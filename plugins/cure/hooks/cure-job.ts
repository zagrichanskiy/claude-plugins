import type { EngineInterface } from 'claude-code'

import type { Outcome } from './work'

/** One row of `cure-job list --json`, as `job_row` in `cli/src/cure_job/commands/list.py` prints it. */
export type ListedJob = {
  id: string
  state: string
  open: number
  ticket: string | null
  'ticket-summary': string | null
  prs: string[]
  branch: string | null
  workspace: string | null
}

export async function exec($: EngineInterface, argv: string[]) {
  try {
    return await $.process.run(argv)
  } catch {
    return null
  }
}

export async function run($: EngineInterface, argv: string[]): Promise<string | null> {
  const result = await exec($, argv)
  return result?.exitCode === 0 ? result.stdout.trim() : null
}

export function cureJobArgv($: EngineInterface, args: string[]) {
  return [`${$.plugin.root}/bin/cure-job`, ...args]
}

export function cureJob($: EngineInterface, args: string[]) {
  return run($, cureJobArgv($, args))
}

export async function githubRepo($: EngineInterface, dir: string | null) {
  const remote = dir === null ? null : await run($, ['git', '-C', dir, 'remote', 'get-url', 'origin'])
  return remote?.match(/github\.com[:/]([^/\s]+\/[^/\s]+?)(?:\.git)?$/)?.[1] ?? null
}

export const failure = (error: unknown) =>
  ({ kind: 'failed', error: error instanceof Error ? error.message : String(error) }) as const

export async function json($: EngineInterface, argv: string[]): Promise<Outcome<unknown>> {
  const result = await exec($, argv)
  if (result === null) return failure(`${argv[0]?.split('/').pop()} did not run`)
  if (result.exitCode !== 0) {
    return failure(result.stderr.trim().split('\n')[0] || `${argv[0]?.split('/').pop()} exited ${result.exitCode}`)
  }
  try {
    return { kind: 'ok', data: JSON.parse(result.stdout) }
  } catch {
    return failure(`${argv[0]?.split('/').pop()} printed no JSON`)
  }
}

export async function listJobs($: EngineInterface): Promise<Outcome<ListedJob[]>> {
  const listed = await json($, cureJobArgv($, ['list', '--json']))
  if (listed.kind !== 'ok') return listed
  return Array.isArray(listed.data) ? { kind: 'ok', data: listed.data as ListedJob[] } : failure('cure-job list printed no job list')
}
