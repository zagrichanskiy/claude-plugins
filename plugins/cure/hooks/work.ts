import type { CureWork, CureWorkChecks, CureWorkJob, CureWorkPr, CureWorkSource, CureWorkTask } from '../types'
import { branchTicket, parseTicket, ticketKey } from './ticket'

export type Task = CureWorkTask
export type Pr = CureWorkPr
export type Job = CureWorkJob
export type Checks = CureWorkChecks
export type Source<T> = CureWorkSource<T>
export type Work = CureWork

export type Outcome<T> =
  | { kind: 'ok'; data: T; partial?: string }
  | { kind: 'failed'; error: string }
  | { kind: 'unavailable'; reason: string }

export type SessionKind = 'pending' | 'dispatcher' | 'job' | 'user' | 'headless'

/** `null` is a fact whose start hook has not fired yet; `pending` waits for it. */
export const sessionKind = (s: { isDispatcher: boolean | null; jobId: string | undefined; isInteractive: boolean | null }): SessionKind =>
  s.isDispatcher === true ? 'dispatcher'
    : s.jobId !== undefined ? 'job'
    : s.isDispatcher === null || s.isInteractive === null ? 'pending'
    : s.isInteractive ? 'user' : 'headless'

export const EMPTY: Work = {
  tasks: { kind: 'unavailable', reason: 'not fetched yet' },
  prs: { kind: 'unavailable', reason: 'not fetched yet' },
  jobs: { kind: 'unavailable', reason: 'not fetched yet' },
  checkedAt: null,
}

/** A failed refresh keeps the last good data, stamped with when it was good. */
export const settle = <T>(prev: Source<T>, outcome: Outcome<T>, now: number): Source<T> => {
  if (outcome.kind === 'ok') return { kind: 'fresh', data: outcome.data, at: now, ...(outcome.partial !== undefined && { partial: outcome.partial }) }
  if (outcome.kind === 'unavailable') return { kind: 'unavailable', reason: outcome.reason }
  return prev.kind === 'unavailable'
    ? { kind: 'unavailable', reason: outcome.error }
    : { kind: 'stale', data: prev.data, at: prev.at, error: outcome.error }
}

/** A PR's last-commit `statusCheckRollup.state`: none without checks, and pending for a state it does not know. */
export const rollup = (state: string | null | undefined): Checks =>
  !state ? 'none' : state === 'SUCCESS' ? 'passing' : state === 'FAILURE' || state === 'ERROR' ? 'failing' : 'pending'

/** Each `field` is a dotted path into the tool's reply; `items` empty means the reply is the list itself. */
export type TasksMcp = {
  server: string
  tool: string
  args: Record<string, unknown>
  field: { items: string; key: string; title: string; status: string; url: string }
}

export type DashboardConfig = {
  refreshSeconds: number
  tracker: string | null
  githubOwners: string[]
  tasksMcp: TasksMcp
  jobStates: string[]
  jobScope: 'workspace' | 'all'
}

const JOB_STATES = ['launched', 'running', 'blocked', 'stalled', 'lost', 'needs-input', 'failed']

const text = (value: unknown): string => (typeof value === 'string' ? value : '')

const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []

/** The dashboard's keys out of `cure-job config get`; `null` (the command failed) gives the defaults. */
export const dashboardConfig = (config: unknown): DashboardConfig => {
  const groups = (config ?? {}) as { split?: { tracker?: unknown }; dashboard?: Record<string, unknown> }
  const dashboard = groups.dashboard ?? {}
  const seconds = dashboard['refresh-seconds']
  const args = dashboard['tasks-mcp-args']
  return {
    refreshSeconds: typeof seconds === 'number' && seconds > 0 ? seconds : 120,
    tracker: typeof groups.split?.tracker === 'string' ? groups.split.tracker : null,
    githubOwners: strings(dashboard['github-owners']),
    tasksMcp: {
      server: text(dashboard['tasks-mcp-server']),
      tool: text(dashboard['tasks-mcp-tool']),
      args: typeof args === 'object' && args !== null && !Array.isArray(args) ? args as Record<string, unknown> : {},
      field: {
        items: text(dashboard['tasks-field-items']), key: text(dashboard['tasks-field-key']),
        title: text(dashboard['tasks-field-title']), status: text(dashboard['tasks-field-status']),
        url: text(dashboard['tasks-field-url']),
      },
    },
    jobStates: Array.isArray(dashboard['job-states']) ? strings(dashboard['job-states']) : JOB_STATES,
    jobScope: dashboard['job-scope'] === 'all' ? 'all' : 'workspace',
  }
}

export const prKey = (pr: Pr): string | null => ticketKey(branchTicket(pr.headRefName), pr.repo)
export const jobKey = (job: Job): string | null => ticketKey(parseTicket(job.ticket), job.repo)

export type TaskGroup = { task: Task; prs: Pr[]; jobs: Job[] }
export type Groups = { tasks: TaskGroup[]; unlinked: { prs: Pr[]; jobs: Job[] } }

export const group = (tasks: readonly Task[], prs: readonly Pr[], jobs: readonly Job[]): Groups => {
  const groups: TaskGroup[] = []
  const byKey = new Map<string, TaskGroup>()
  for (const task of tasks) {
    if (byKey.has(task.key)) continue
    const entry: TaskGroup = { task, prs: [], jobs: [] }
    groups.push(entry)
    for (const key of [task.key, ...task.aliases]) if (!byKey.has(key)) byKey.set(key, entry)
  }
  const unlinked: Groups['unlinked'] = { prs: [], jobs: [] }
  for (const pr of prs) (byKey.get(prKey(pr) ?? '') ?? unlinked).prs.push(pr)
  for (const job of jobs) (byKey.get(jobKey(job) ?? '') ?? unlinked).jobs.push(job)
  return { tasks: groups, unlinked }
}

export const dataOf = <T>(source: Source<T[]>): T[] => (source.kind === 'unavailable' ? [] : source.data)

export const age = (at: number, now: number): string => {
  const minutes = Math.max(0, Math.floor((now - at) / 60000))
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`
}
