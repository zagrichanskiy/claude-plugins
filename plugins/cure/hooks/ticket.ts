export type Ticket =
  | { kind: 'url'; url: string }
  | { kind: 'tracker'; key: string }
  | { kind: 'issue'; repo: string | null; number: string }

const TRACKER_KEY = /^[A-Z]+-[0-9]+$/

export const parseTicket = (ticket: string | null): Ticket | null => {
  if (ticket === null) return null
  if (/^https?:\/\/\S+$/.test(ticket)) return { kind: 'url', url: ticket }
  if (TRACKER_KEY.test(ticket)) return { kind: 'tracker', key: ticket }
  const issue = ticket.match(/^([\w.-]+\/[\w.-]+)?#([0-9]+)$/)
  return issue === null ? null : { kind: 'issue', repo: issue[1] ?? null, number: issue[2] ?? '' }
}

export const branchTicket = (branch: string | null): Ticket | null => {
  const tracker = branch?.match(/^([A-Z]+-[0-9]+)[_-]/)
  if (tracker) return { kind: 'tracker', key: tracker[1] ?? '' }
  const issue = branch?.match(/^issue-([0-9]+)[_-]/)
  return issue ? { kind: 'issue', repo: null, number: issue[1] ?? '' } : null
}

const GITHUB_ISSUE_URL = /^https?:\/\/(?:www\.)?github\.com\/([\w.-]+\/[\w.-]+)\/issues\/([0-9]+)(?:[/?#]\S*)?$/
const CLICKUP_TASK_URL = /^https?:\/\/app\.clickup\.com\/t\/(?:[^/?#]+\/)?([^/?#]+)\/?(?:[?#]\S*)?$/

const urlKey = (url: string): string | null => {
  const issue = url.match(GITHUB_ISSUE_URL)
  if (issue) return `${issue[1]}#${issue[2]}`
  return url.match(CLICKUP_TASK_URL)?.[1] ?? null
}

/**
 * A tracker key, or `owner/repo#N` with `repo` standing in for a ticket that names no repository.
 * A GitHub issue URL keys as `owner/repo#N`; a ClickUp task URL as its last segment, the custom id
 * under `/t/<workspace-id>/` and the task id otherwise.
 */
export const ticketKey = (ticket: Ticket | null, repo: string | null): string | null => {
  if (ticket?.kind === 'tracker') return ticket.key
  if (ticket?.kind === 'url') return urlKey(ticket.url)
  if (ticket?.kind !== 'issue') return null
  const owner = ticket.repo ?? repo
  return owner === null ? null : `${owner}#${ticket.number}`
}
