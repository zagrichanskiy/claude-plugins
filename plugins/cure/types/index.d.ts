export type CureBand = { isDispatcher: boolean | null }

/** `key` is the one drawn; `aliases` are further keys a ticket may name it by, as a ClickUp task's id beside its custom id. */
export type CureWorkTask = { key: string; aliases: string[]; title: string; status: string }

export type CureWorkChecks = 'passing' | 'failing' | 'pending' | 'none'

export type CureWorkPr = {
  repo: string
  number: number
  title: string
  state: string
  reviewDecision: string | null
  checks: CureWorkChecks
  headRefName: string | null
  url: string
}

export type CureWorkJob = { id: string; state: string; ticket: string | null; repo: string | null }

export type CureWorkSource<T> =
  | { kind: 'unavailable'; reason: string }
  | { kind: 'fresh'; data: T; at: number }
  | { kind: 'stale'; data: T; at: number; error: string }

export type CureWork = {
  tasks: CureWorkSource<CureWorkTask[]>
  prs: CureWorkSource<CureWorkPr[]>
  jobs: CureWorkSource<CureWorkJob[]>
  checkedAt: number | null
}

declare module 'claude-code' {
  interface PluginState {
    cure: { isDispatcher: boolean | null; isInteractive: boolean | null; isWorkClosed: boolean; work: Shaped<CureWork> }
  }
}
