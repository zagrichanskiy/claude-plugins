import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

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

const exec = async ($: EngineInterface, argv: string[]) => {
  try {
    return await $.process.run(argv)
  } catch {
    return null
  }
}

const run = async ($: EngineInterface, argv: string[]): Promise<string | null> => {
  const result = await exec($, argv)
  return result?.exitCode === 0 ? result.stdout.trim() : null
}

const cureJobArgv = ($: EngineInterface, args: string[]) => [`${$.plugin.root}/bin/cure-job`, ...args]
const cureJob = ($: EngineInterface, args: string[]) => run($, cureJobArgv($, args))

const JIRA_KEY = /^[A-Z]+-[0-9]+$/

const jiraSite = async ($: EngineInterface): Promise<string | null> => {
  const site = await cureJob($, ['config', 'get', 'band.jira-url'])
  try {
    return site === null ? null : (JSON.parse(site) as string).replace(/\/+$/, '')
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

const githubRepo = async ($: EngineInterface, dir: string | null) => {
  const remote = dir === null ? null : await run($, ['git', '-C', dir, 'remote', 'get-url', 'origin'])
  return remote?.match(/github\.com[:/]([^/\s]+\/[^/\s]+?)(?:\.git)?$/)?.[1] ?? null
}

const ticketUrl = async ($: EngineInterface, job: Job, jira: string | null): Promise<string | null> => {
  const ticket = job.ticket ?? ''
  if (/^https?:\/\/\S+$/.test(ticket)) return ticket
  if (JIRA_KEY.test(ticket)) return jira === null ? null : `${jira}/browse/${ticket}`
  const issue = ticket.match(/^([\w.-]+\/[\w.-]+)?#([0-9]+)$/)
  if (issue === null) return null
  const repo = issue[1] ?? (await githubRepo($, job.workspace))
  return repo === null ? null : `https://github.com/${repo}/issues/${issue[2]}`
}

type Row = { job: Job; url: string | null; branch: string | null; dir: string | null }

export const register: Register = on => {
  on('classic.SessionStart', async ($, e, next) => {
    await update($, isDispatcher, () => e.agent_type === 'cure:dispatcher')
    return next(e)
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

    const jira = jobs.some(job => JIRA_KEY.test(job.ticket ?? '')) ? await jiraSite($) : null
    const rows: Row[] = []
    for (const job of jobs) {
      const url = await ticketUrl($, job, jira)
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
