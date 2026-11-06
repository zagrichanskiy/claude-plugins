import type { EngineInterface } from 'claude-code'

import { cureJob, failure, githubRepo, json, listJobs } from './cure-job'
import { parseTicket } from './ticket'
import { dashboardConfig, rollup } from './work'
import type { CheckItem, DashboardConfig, Job, Outcome, Pr, Task } from './work'

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

type Hit = { number: number; title: string; state: string; url: string; repository: { nameWithOwner: string } }
type View = { headRefName?: string; reviewDecision?: string; statusCheckRollup?: CheckItem[]; state?: string }

const SEARCH = ['--state', 'open', '--limit', '100', '--json']

async function fetchPrs($: EngineInterface): Promise<Outcome<Pr[]>> {
  const hits = new Map<string, Hit>()
  for (const who of ['--author', '--review-requested']) {
    const found = await json($, ['gh', 'search', 'prs', who, '@me', ...SEARCH, 'number,title,repository,url,state'])
    if (found.kind !== 'ok') return found
    for (const hit of found.data as Hit[]) hits.set(hit.url, hit)
  }
  const prs: Pr[] = []
  for (const hit of hits.values()) {
    const repo = hit.repository.nameWithOwner
    const viewed = await json($, ['gh', 'pr', 'view', String(hit.number), '-R', repo,
      '--json', 'headRefName,reviewDecision,statusCheckRollup,state,url'])
    const view = viewed.kind === 'ok' ? (viewed.data as View) : null
    prs.push({
      repo, number: hit.number, title: hit.title, url: hit.url,
      state: view?.state ?? hit.state,
      reviewDecision: view?.reviewDecision || null,
      checks: view === null ? 'unknown' : rollup(view.statusCheckRollup),
      headRefName: view?.headRefName ?? null,
    })
  }
  return { kind: 'ok', data: prs }
}

async function fetchJobs($: EngineInterface): Promise<Outcome<Job[]>> {
  const listed = await listJobs($)
  if (listed.kind !== 'ok') return listed
  const repos = new Map<string, string | null>()
  const jobs: Job[] = []
  for (const job of listed.data) {
    const ticket = parseTicket(job.ticket)
    const dir = ticket?.kind === 'issue' && ticket.repo === null ? job.workspace : null
    if (dir !== null && !repos.has(dir)) repos.set(dir, await githubRepo($, dir))
    jobs.push({ id: job.id, state: job.state, ticket: job.ticket, repo: dir === null ? null : repos.get(dir) ?? null })
  }
  return { kind: 'ok', data: jobs }
}

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

type ClickupTask = { id: string; custom_id?: string | null; name: string; status?: string | { status?: string } }
type ClickupPage = { tasks: ClickupTask[]; has_more?: boolean; next_page?: number }

const CLICKUP_PAGES = 10

async function clickupTasks($: EngineInterface, config: DashboardConfig): Promise<Outcome<Task[]>> {
  const tools = await $.tool.list()
  const server = tools.map(tool => tool.name.match(/^mcp__(.+)__clickup_filter_tasks$/)?.[1]).find(Boolean) ?? 'clickup'
  const filter = {
    assignees: ['me'], include_closed: false, fields: ['custom_id', 'status'],
    ...(config.clickupSpaces.length > 0 && { space_ids: config.clickupSpaces }),
    ...(config.clickupLists.length > 0 && { list_ids: config.clickupLists }),
  }
  const tasks: Task[] = []
  let page: number | undefined = 0
  for (let pages = 0; page !== undefined && pages < CLICKUP_PAGES; pages++) {
    const result = await $.mcp.call(server, 'clickup_filter_tasks', { ...filter, page })
    const text = result.content.find(block => block.type === 'text')?.text ?? ''
    if (result.isError) return failure(`ClickUp: ${text.split('\n')[0] || 'the call failed'}`)
    const body = (result.structuredContent ?? JSON.parse(text)) as Partial<ClickupPage> | null
    if (!Array.isArray(body?.tasks)) return failure('ClickUp: the reply holds no task list')
    for (const task of body.tasks) {
      const status = typeof task.status === 'string' ? task.status : task.status?.status ?? ''
      tasks.push({ key: task.custom_id || task.id, aliases: task.custom_id ? [task.id] : [], title: task.name, status })
    }
    page = body.has_more ? body.next_page : undefined
  }
  return { kind: 'ok', data: tasks }
}

function fetchTasks($: EngineInterface, config: DashboardConfig): Promise<Outcome<Task[]>> {
  if (config.tracker === 'github') return githubTasks($, config.githubOwners)
  if (config.tracker === 'clickup') return clickupTasks($, config)
  return Promise.resolve({ kind: 'unavailable', reason: `split.tracker ${config.tracker ?? '(unread)'} has no task source` })
}

export async function fetchWork($: EngineInterface, config: DashboardConfig) {
  const [tasks, prs, jobs] = await Promise.all([
    guarded(() => fetchTasks($, config)), guarded(() => fetchPrs($)), guarded(() => fetchJobs($)),
  ])
  return { tasks, prs, jobs }
}
