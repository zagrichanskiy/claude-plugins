import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import { parseTicket } from './ticket'
import { EMPTY, sessionKind, settle } from './work'
import type { DashboardConfig } from './work'
import { cureJob, cureJobArgv, exec, fetchWork, githubRepo, readConfig, run } from './work-fetch'
import { drawWork } from './work-pane'

type Job = {
  id: string
  state: string
  open: number
  ticket: string | null
  'ticket-summary': string | null
  prs: string[]
  branch: string | null
  workspace: string | null
}

const isDispatcher = atom({ plugin: 'cure', key: 'isDispatcher' } as const, false)
const isInteractive = atom({ plugin: 'cure', key: 'isInteractive' } as const, false)
const work = atom({ plugin: 'cure', key: 'work' } as const, EMPTY, { shape: 'work-1' })

const PANE = 'work'

const trackerUrl = async ($: EngineInterface): Promise<string | null> => {
  const url = await cureJob($, ['config', 'get', 'band.tracker-url'])
  try {
    return url === null ? null : (JSON.parse(url) as string)
  } catch {
    return null
  }
}

const listJobs = async ($: EngineInterface): Promise<Job[]> => {
  const out = await cureJob($, ['list', '--json'])
  try {
    return out === null ? [] : (JSON.parse(out) as Job[])
  } catch {
    return []
  }
}

const ticketUrl = async ($: EngineInterface, job: Job, tracker: string | null): Promise<string | null> => {
  const ticket = parseTicket(job.ticket)
  if (ticket?.kind === 'url') return ticket.url
  if (ticket?.kind === 'tracker') return tracker === null ? null : tracker.replaceAll('<key>', ticket.key)
  if (ticket?.kind !== 'issue') return null
  const repo = ticket.repo ?? (await githubRepo($, job.workspace))
  return repo === null ? null : `https://github.com/${repo}/issues/${ticket.number}`
}

let timer: { cancel: () => void } | null = null
let isRefreshing = false

const refresh = async ($: EngineInterface, config: DashboardConfig) => {
  if (isRefreshing) return
  isRefreshing = true
  try {
    const fetched = await fetchWork($, config)
    const now = await $.clock.now()
    await update($, work, prev => ({
      tasks: settle(prev.tasks, fetched.tasks, now),
      prs: settle(prev.prs, fetched.prs, now),
      jobs: settle(prev.jobs, fetched.jobs, now),
      checkedAt: now,
    }))
  } catch (error) {
    $.ui.log(`work pane: refresh failed: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    isRefreshing = false
  }
}

/** Both start hooks call it: which of them fires first is not known, and each settles part of the session's kind. */
const startDashboard = async ($: EngineInterface) => {
  const kind = sessionKind({
    isDispatcher: await read($, isDispatcher),
    jobId: await $.env.get('CURE_JOB_ID'),
    isInteractive: await read($, isInteractive),
  })
  if (kind !== 'user') {
    timer?.cancel()
    timer = null
    if ((await $.ui.panes()).some(pane => pane.id === PANE)) await $.ui.close({ id: PANE })
    return
  }
  if (timer !== null) return
  const starting = { cancel: () => {} }
  timer = starting
  const config = await readConfig($)
  if (timer !== starting) return
  timer = $.clock.every(config.refreshSeconds * 1000, () => void refresh($, config))
  void $.ui.open({ id: PANE, title: 'Work' })
  void refresh($, config)
}

type Row = { job: Job; url: string | null; branch: string | null; dir: string | null }

export const register: Register = on => {
  on('classic.SessionStart', async ($, e, next) => {
    await update($, isDispatcher, () => e.agent_type === 'cure:dispatcher')
    await startDashboard($)
    return next(e)
  })

  on('session.start', async ($, e, next) => {
    await update($, isInteractive, () => e.isInteractive)
    await startDashboard($)
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Link } = $.ui.resolve(e)
    return drawWork({ Box, Text, Link }, await read($, work), await $.clock.now())
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const isBoard = await read($, isDispatcher)
    const jobId = isBoard ? undefined : await $.env.get('CURE_JOB_ID')
    if (jobId === undefined && !isBoard) return next(e)

    const jobs = (await listJobs($)).filter(job =>
      isBoard ? job.state === 'awaiting-approval' : job.id === jobId,
    )
    if (jobs.length === 0) return next(e)

    const tracker = jobs.some(job => parseTicket(job.ticket)?.kind === 'tracker') ? await trackerUrl($) : null
    const rows: Row[] = []
    for (const job of jobs) {
      const url = await ticketUrl($, job, tracker)
      if (isBoard) {
        rows.push({ job, url, branch: job.branch, dir: job.workspace })
        continue
      }
      const dir = await $.session.cwd()
      const branch = job.branch ?? (await run($, ['git', '-C', dir, 'branch', '--show-current']))
      rows.push({ job, url, branch: branch || null, dir })
    }

    const { Box, Button, Link, Text } = $.ui.resolve(e)
    const press = (job: Job, said: string, args: string[]) => async () => {
      const result = await exec($, cureJobArgv($, args))
      if (result?.exitCode === 0) {
        void $.prompt.submit({ text: `${said} job ${job.id} from the band; rescan.` })
          .catch(() => $.ui.toast(`the dispatcher was not told: ${said} job ${job.id}`))
      } else {
        const reason = result?.stderr.trim().split('\n')[0]
        $.ui.toast(`cure-job ${args[0]} ${job.id} failed${reason ? `: ${reason}` : ''}`)
      }
      $.ui.invalidate('ui.render')
    }

    return (
      <Box flexDirection="column">
        {rows.map(({ job, url, branch, dir }) => (
          <Box key={job.id} flexDirection="column">
            <Text>
              {job.ticket === null ? job.id : url === null ? job.ticket : <Link href={url}>{job.ticket}</Link>}
              {job['ticket-summary'] === null ? '' : ` ${job['ticket-summary']}`}
            </Text>
            <Text dimColor>
              {job.prs.map(pr => (
                <Link href={pr}>{`${pr} `}</Link>
              ))}
              {branch === null ? '' : `${branch} `}
              {dir ?? ''}
            </Text>
            {isBoard && (
              <Box>
                {job.open === 0 && (
                  <Button key={`approve-${job.id}`} label="Approve" variant="primary"
                    onPress={press(job, 'Approved', ['approve', job.id, '--by', 'user'])} />
                )}
                <Button key={`reject-${job.id}`} label="Reject" onPress={press(job, 'Rejected', ['close', job.id])} />
              </Box>
            )}
          </Box>
        ))}
      </Box>
    )
  })
}
