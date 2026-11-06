import type { CureWork, CureWorkChecks, CureWorkJob, CureWorkPr, CureWorkSource, CureWorkTask } from '../types'
import { branchTicket, parseTicket, ticketKey } from './ticket'

export type Task = CureWorkTask
export type Pr = CureWorkPr
export type Job = CureWorkJob
export type Checks = CureWorkChecks
export type Source<T> = CureWorkSource<T>
export type Work = CureWork

export type Outcome<T> =
  | { kind: 'ok'; data: T }
  | { kind: 'failed'; error: string }
  | { kind: 'unavailable'; reason: string }

export type SessionKind = 'dispatcher' | 'job' | 'user' | 'headless'

export const sessionKind = (s: { isDispatcher: boolean; jobId: string | undefined; isInteractive: boolean }): SessionKind =>
  s.isDispatcher ? 'dispatcher' : s.jobId !== undefined ? 'job' : s.isInteractive ? 'user' : 'headless'

export const EMPTY: Work = {
  tasks: { kind: 'unavailable', reason: 'not fetched yet' },
  prs: { kind: 'unavailable', reason: 'not fetched yet' },
  jobs: { kind: 'unavailable', reason: 'not fetched yet' },
  checkedAt: null,
}

/** A failed refresh keeps the last good data, stamped with when it was good. */
export const settle = <T>(prev: Source<T>, outcome: Outcome<T>, now: number): Source<T> => {
  if (outcome.kind === 'ok') return { kind: 'fresh', data: outcome.data, at: now }
  if (outcome.kind === 'unavailable') return { kind: 'unavailable', reason: outcome.reason }
  return prev.kind === 'unavailable'
    ? { kind: 'unavailable', reason: outcome.error }
    : { kind: 'stale', data: prev.data, at: prev.at, error: outcome.error }
}

export type CheckItem = { status?: string | null; conclusion?: string | null; state?: string | null }

const FAILED = new Set(['FAILURE', 'ERROR', 'TIMED_OUT', 'CANCELLED', 'ACTION_REQUIRED', 'STARTUP_FAILURE'])
const PASSED = new Set(['SUCCESS', 'NEUTRAL', 'SKIPPED'])

/** One state for a PR's `statusCheckRollup`; an item in any state it does not know counts as pending. */
export const rollup = (items: readonly CheckItem[] | null | undefined): Checks => {
  if (!Array.isArray(items)) return 'unknown'
  if (items.length === 0) return 'none'
  const states = items.map(item => (item.conclusion || item.state || item.status || '').toUpperCase())
  if (states.some(state => FAILED.has(state))) return 'failing'
  return states.every(state => PASSED.has(state)) ? 'passing' : 'pending'
}

export type DashboardConfig = {
  refreshSeconds: number
  tracker: string | null
  githubOwners: string[]
  clickupSpaces: string[]
  clickupLists: string[]
}

const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []

/** The dashboard's keys out of `cure-job config get`; `null` (the command failed) gives the defaults. */
export const dashboardConfig = (config: unknown): DashboardConfig => {
  const groups = (config ?? {}) as { split?: { tracker?: unknown }; dashboard?: Record<string, unknown> }
  const dashboard = groups.dashboard ?? {}
  const seconds = dashboard['refresh-seconds']
  return {
    refreshSeconds: typeof seconds === 'number' && seconds > 0 ? seconds : 120,
    tracker: typeof groups.split?.tracker === 'string' ? groups.split.tracker : null,
    githubOwners: strings(dashboard['github-owners']),
    clickupSpaces: strings(dashboard['clickup-spaces']),
    clickupLists: strings(dashboard['clickup-lists']),
  }
}

export const prKey = (pr: Pr): string | null => ticketKey(branchTicket(pr.headRefName), pr.repo)
export const jobKey = (job: Job): string | null => ticketKey(parseTicket(job.ticket), job.repo)

export type TaskGroup = { task: Task; prs: Pr[]; jobs: Job[] }
export type Groups = { tasks: TaskGroup[]; unlinked: { prs: Pr[]; jobs: Job[] } }

export const group = (tasks: readonly Task[], prs: readonly Pr[], jobs: readonly Job[]): Groups => {
  const byKey = new Map<string, TaskGroup>(tasks.map(task => [task.key, { task, prs: [], jobs: [] }]))
  const unlinked: Groups['unlinked'] = { prs: [], jobs: [] }
  for (const pr of prs) (byKey.get(prKey(pr) ?? '') ?? unlinked).prs.push(pr)
  for (const job of jobs) (byKey.get(jobKey(job) ?? '') ?? unlinked).jobs.push(job)
  return { tasks: [...byKey.values()], unlinked }
}

export const dataOf = <T>(source: Source<T[]>): T[] => (source.kind === 'unavailable' ? [] : source.data)

export const age = (at: number, now: number): string => {
  const minutes = Math.max(0, Math.floor((now - at) / 60000))
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`
}
