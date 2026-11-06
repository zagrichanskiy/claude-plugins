import type { EngineInterface } from 'claude-code'

import { cureJob, exec, failure, githubRepo, json, listJobs } from './cure-job'
import { parseTicket, ticketKey } from './ticket'
import { dashboardConfig, rollup } from './work'
import type { DashboardConfig, Job, Outcome, Pr, Task, TasksMcp } from './work'

const guarded = async <T>(fetch: () => Promise<Outcome<T>>): Promise<Outcome<T>> => {
  try {
    return await fetch()
  } catch (error) {
    return failure(error)
  }
}

export async function readConfig($: EngineInterface): Promise<DashboardConfig> {
  const out = await cureJob($, ['config', 'get'])
  try {
    return dashboardConfig(out === null ? null : JSON.parse(out))
  } catch {
    return dashboardConfig(null)
  }
}

type Hit = {
  number: number; title: string; state: string; url: string; headRefName: string; reviewDecision: string | null
  repository: { nameWithOwner: string }; commits: { nodes: { commit: { statusCheckRollup: { state: string } | null } }[] }
}

const PR_QUERY = `query($q: String!) { search(type: ISSUE, query: $q, first: 100) { nodes { ... on PullRequest {
  number title url state headRefName reviewDecision repository { nameWithOwner }
  commits(last: 1) { nodes { commit { statusCheckRollup { state } } } } } } } }`

/** `gh api graphql` exits non-zero on a partial error (one SSO-forbidden org), yet prints the nodes it could read; `partial` is its first stderr line then. */
async function searchNodes($: EngineInterface, q: string): Promise<Outcome<unknown[]>> {
  const result = await exec($, ['gh', 'api', 'graphql', '-f', `query=${PR_QUERY}`, '-f', `q=${q}`])
  if (result === null) return failure('gh did not run')
  let nodes: unknown
  try {
    nodes = (JSON.parse(result.stdout) as { data?: { search?: { nodes?: unknown } } } | null)?.data?.search?.nodes
  } catch {
    nodes = undefined
  }
  const reason = result.stderr.trim().split('\n')[0] || `gh exited ${result.exitCode}`
  if (Array.isArray(nodes)) return { kind: 'ok', data: nodes, ...(result.exitCode !== 0 && { partial: reason }) }
  if (result.exitCode !== 0) return failure(reason)
  return failure('gh api graphql printed no search result')
}

const isHit = (node: unknown): node is Hit => {
  const hit = node as Partial<Hit> | null
  return typeof hit?.url === 'string' && typeof hit.repository?.nameWithOwner === 'string' && Array.isArray(hit.commits?.nodes)
}

async function fetchPrs($: EngineInterface, owners: string[]): Promise<Outcome<Pr[]>> {
  const hits = new Map<string, Hit>()
  let partial: string | undefined
  for (const role of ['author', 'review-requested']) {
    const q = ['is:pr', 'is:open', `${role}:@me`, ...owners.map(owner => `user:${owner}`)].join(' ')
    const found = await searchNodes($, q)
    if (found.kind !== 'ok') return found
    partial ??= found.partial
    for (const hit of found.data.filter(isHit)) hits.set(hit.url, hit)
  }
  return {
    kind: 'ok',
    data: [...hits.values()].map(hit => ({
      repo: hit.repository.nameWithOwner, number: hit.number, title: hit.title, url: hit.url, state: hit.state,
      reviewDecision: hit.reviewDecision || null,
      checks: rollup(hit.commits.nodes[0]?.commit.statusCheckRollup?.state),
      headRefName: hit.headRefName,
    })),
    ...(partial !== undefined && { partial }),
  }
}

async function fetchJobs($: EngineInterface, config: DashboardConfig): Promise<Outcome<Job[]>> {
  const listed = await listJobs($)
  if (listed.kind !== 'ok') return listed
  const here = config.jobScope === 'workspace' ? await $.session.root() : null
  const repos = new Map<string, string | null>()
  const jobs: Job[] = []
  for (const job of listed.data) {
    if (!config.jobStates.includes(job.state) || (here !== null && job.workspace !== here)) continue
    const ticket = parseTicket(job.ticket)
    const dir = ticket?.kind === 'issue' && ticket.repo === null ? job.workspace : null
    if (dir !== null && !repos.has(dir)) repos.set(dir, await githubRepo($, dir))
    jobs.push({ id: job.id, state: job.state, ticket: job.ticket, repo: dir === null ? null : repos.get(dir) ?? null })
  }
  return { kind: 'ok', data: jobs }
}

const SEARCH = ['--state', 'open', '--limit', '100', '--json']

type Issue = { number: number; title: string; state: string; repository: { nameWithOwner: string } }

async function githubTasks($: EngineInterface, owners: string[]): Promise<Outcome<Task[]>> {
  const tasks: Task[] = []
  for (const scope of owners.length === 0 ? [[]] : owners.map(owner => ['--owner', owner])) {
    const found = await json($, ['gh', 'search', 'issues', '--assignee', '@me', ...scope, ...SEARCH,
      'number,title,repository,state'])
    if (found.kind !== 'ok') return found
    for (const issue of found.data as Issue[]) {
      tasks.push({ key: `${issue.repository.nameWithOwner}#${issue.number}`, aliases: [], title: issue.title, status: issue.state })
    }
  }
  return { kind: 'ok', data: tasks }
}

const at = (value: unknown, path: string): unknown =>
  path === '' ? value : path.split('.').reduce<unknown>((node, name) => (node as Record<string, unknown> | null)?.[name], value)

const scalar = (value: unknown): string => (typeof value === 'string' || typeof value === 'number' ? String(value) : '')

async function mcpTasks($: EngineInterface, { server, tool, args, field }: TasksMcp): Promise<Outcome<Task[]>> {
  const result = await $.mcp.call(server, tool, args)
  const text = result.content.find(block => block.type === 'text')?.text ?? ''
  const name = `${server} ${tool}`
  if (result.isError) return failure(`${name}: ${text.split('\n')[0] || 'the call failed'}`)
  const items = at(result.structuredContent ?? JSON.parse(text), field.items)
  if (!Array.isArray(items)) return failure(`${name}: the reply holds no list at "${field.items}"`)
  const tasks: Task[] = []
  for (const item of items) {
    const key = scalar(at(item, field.key))
    if (key === '') continue
    const url = field.url === '' ? '' : scalar(at(item, field.url))
    tasks.push({
      key, aliases: url === '' ? [] : [ticketKey({ kind: 'url', url }, null) ?? url],
      title: field.title === '' ? '' : scalar(at(item, field.title)),
      status: field.status === '' ? '' : scalar(at(item, field.status)),
    })
  }
  return { kind: 'ok', data: tasks }
}

function fetchTasks($: EngineInterface, config: DashboardConfig): Promise<Outcome<Task[]>> {
  if (config.tracker === 'github') return githubTasks($, config.githubOwners)
  const { server, tool, field } = config.tasksMcp
  if (server !== '' && tool !== '' && field.key !== '') return mcpTasks($, config.tasksMcp)
  return Promise.resolve({ kind: 'unavailable', reason: `split.tracker ${config.tracker ?? '(unread)'} has no task source and no dashboard.tasks-mcp-server, tasks-mcp-tool and tasks-field-key` })
}

export async function fetchWork($: EngineInterface, config: DashboardConfig) {
  const [tasks, prs, jobs] = await Promise.all([
    guarded(() => fetchTasks($, config)), guarded(() => fetchPrs($, config.githubOwners)), guarded(() => fetchJobs($, config)),
  ])
  return { tasks, prs, jobs }
}
