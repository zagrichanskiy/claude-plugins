import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import { cureJob, cureJobArgv, exec, failure, githubRepo, listJobs, run } from './cure-job'
import type { ListedJob } from './cure-job'
import { parseTicket } from './ticket'
import { EMPTY, sessionKind, settle } from './work'
import type { DashboardConfig, Work } from './work'
import { fetchWork, readConfig } from './work-fetch'
import { drawWork } from './work-pane'

const isDispatcher = atom({ plugin: 'cure', key: 'isDispatcher' } as const, null)
const isInteractive = atom({ plugin: 'cure', key: 'isInteractive' } as const, null)
const work = atom({ plugin: 'cure', key: 'work' } as const, EMPTY, { shape: 'work-2' })

const PANE = 'work'

const trackerUrl = async ($: EngineInterface): Promise<string | null> => {
  const url = await cureJob($, ['config', 'get', 'band.tracker-url'])
  try {
    return url === null ? null : (JSON.parse(url) as string)
  } catch {
    return null
  }
}

const ticketUrl = async ($: EngineInterface, job: ListedJob, tracker: string | null): Promise<string | null> => {
  const ticket = parseTicket(job.ticket)
  if (ticket?.kind === 'url') return ticket.url
  if (ticket?.kind === 'tracker') return tracker === null ? null : tracker.replaceAll('<key>', ticket.key)
  if (ticket?.kind !== 'issue') return null
  const repo = ticket.repo ?? (await githubRepo($, job.workspace))
  return repo === null ? null : `https://github.com/${repo}/issues/${ticket.number}`
}

let isStarted = false
let timer: { cancel: () => void } | null = null
let isRefreshing = false

const settled = (prev: Work, fetched: Awaited<ReturnType<typeof fetchWork>>, now: number): Work => ({
  tasks: settle(prev.tasks, fetched.tasks, now),
  prs: settle(prev.prs, fetched.prs, now),
  jobs: settle(prev.jobs, fetched.jobs, now),
  checkedAt: now,
})

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

const refresh = async ($: EngineInterface, config: DashboardConfig) => {
  if (isRefreshing) return
  isRefreshing = true
  let now: number | null = null
  try {
    const fetched = await fetchWork($, config)
    now = await $.clock.now()
    const at = now
    await update($, work, prev => settled(prev, fetched, at))
  } catch (error) {
    $.ui.log(`work pane: refresh failed: ${message(error)}`)
    const failed = failure(error)
    try {
      await update($, work, prev => settled(prev, { tasks: failed, prs: failed, jobs: failed }, now ?? prev.checkedAt ?? 0))
    } catch (again) {
      $.ui.log(`work pane: the failed refresh was not recorded: ${message(again)}`)
    }
  } finally {
    isRefreshing = false
  }
}

/** Both start hooks call it; each supplies one fact of the session's kind, in an order that is not known. */
const startDashboard = async ($: EngineInterface) => {
  const kind = sessionKind({
    isDispatcher: await read($, isDispatcher),
    jobId: await $.env.get('CURE_JOB_ID'),
    isInteractive: await read($, isInteractive),
  })
  if (kind !== 'user' || isStarted) return
  isStarted = true
  const config = await readConfig($)
  timer = $.clock.every(config.refreshSeconds * 1000, () => void refresh($, config))
  void $.ui.open({ id: PANE, title: 'Work' })
  void refresh($, config)
}

const startInBackground = ($: EngineInterface) =>
  void startDashboard($).catch(error => $.ui.log(`work pane: start failed: ${message(error)}`))

type Row = { job: ListedJob; url: string | null; branch: string | null; dir: string | null }

export const register: Register = on => {
  on('classic.SessionStart', async ($, e, next) => {
    await update($, isDispatcher, () => e.agent_type === 'cure:dispatcher')
    const result = await next(e)
    startInBackground($)
    return result
  })

  on('session.start', async ($, e, next) => {
    await update($, isInteractive, () => e.isInteractive)
    const result = await next(e)
    startInBackground($)
    return result
  })

  on('ui.close', { id: PANE }, async ($, e, next) => {
    const closed = await next(e)
    if (e.origin.kind === 'person') {
      timer?.cancel()
      timer = null
    }
    return closed
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

    const listed = await listJobs($)
    const jobs = (listed.kind === 'ok' ? listed.data : []).filter(job =>
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
    const press = (job: ListedJob, said: string, args: string[]) => async () => {
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
