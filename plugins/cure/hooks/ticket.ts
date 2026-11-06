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
const urlKey = (url: string): string => {
  const issue = url.match(GITHUB_ISSUE_URL)
  return issue ? `${issue[1]}#${issue[2]}` : url
}

/**
 * A tracker key, or `owner/repo#N` with `repo` standing in for a ticket that names no repository.
 * A GitHub issue URL keys as `owner/repo#N`; any other URL keys as itself, which a task's URL alias matches.
 */
export const ticketKey = (ticket: Ticket | null, repo: string | null): string | null => {
  if (ticket?.kind === 'tracker') return ticket.key
  if (ticket?.kind === 'url') return urlKey(ticket.url)
  if (ticket?.kind !== 'issue') return null
  const owner = ticket.repo ?? repo
  return owner === null ? null : `${owner}#${ticket.number}`
}
