import type { BoxProps, ElementConstructor, LinkProps, TextProps } from 'claude-code'

import { age, dataOf, group } from './work'
import type { Job, Pr, Source, Work } from './work'

export type PaneElements = {
  Box: ElementConstructor<BoxProps>
  Text: ElementConstructor<TextProps>
  Link: ElementConstructor<LinkProps>
}

export const note = (name: string, source: Source<unknown[]>, now: number): string | null => {
  if (source.kind === 'unavailable') return `${name} unavailable: ${source.reason}`
  if (source.kind === 'stale') return `${name} as of ${age(source.at, now)} ago: ${source.error}`
  return source.partial === undefined ? null : `${name} incomplete: ${source.partial}`
}

const words = (value: string) => value.toLowerCase().replaceAll('_', ' ')

export const prText = (pr: Pr): string =>
  ` ${pr.title} · ${words(pr.state)}${pr.reviewDecision === null ? '' : ` · ${words(pr.reviewDecision)}`} · checks ${pr.checks}`

export const jobText = (job: Job): string => `job ${job.id} ${job.state}`

export const drawWork = ({ Box, Text, Link }: PaneElements, work: Work, now: number) => {
  if (work.checkedAt === null) return <Text dimColor>Fetching tasks, PRs and jobs.</Text>
  const { tasks, unlinked } = group(dataOf(work.tasks), dataOf(work.prs), dataOf(work.jobs))
  const notes = [note('Tasks', work.tasks, now), note('PRs', work.prs, now), note('Jobs', work.jobs, now)]
  const items = (prs: Pr[], jobs: Job[]) => [
    ...prs.map(pr => (
      <Text>
        {'  '}
        <Link href={pr.url}>{`${pr.repo}#${pr.number}`}</Link>
        {prText(pr)}
      </Text>
    )),
    ...jobs.map(job => <Text dimColor>{`  ${jobText(job)}`}</Text>),
  ]
  const isEmpty = tasks.length === 0 && unlinked.prs.length === 0 && unlinked.jobs.length === 0
  return (
    <Box flexDirection="column">
      {notes.map(line => line !== null && <Text color="yellow">{line}</Text>)}
      {isEmpty && <Text dimColor>No open tasks, PRs or jobs.</Text>}
      {tasks.map(({ task, prs, jobs }) => (
        <Box key={`task-${task.key}`} flexDirection="column">
          <Text weight="bold">
            {`${task.key} ${task.title}`}
            <Text dimColor>{` · ${task.status}`}</Text>
          </Text>
          {items(prs, jobs)}
        </Box>
      ))}
      {(unlinked.prs.length > 0 || unlinked.jobs.length > 0) && (
        <Box key="unlinked" flexDirection="column">
          <Text weight="bold">Unlinked</Text>
          {items(unlinked.prs, unlinked.jobs)}
        </Box>
      )}
    </Box>
  )
}
