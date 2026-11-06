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

/** A tracker key, or `owner/repo#N` with `repo` standing in for a ticket that names no repository. */
export const ticketKey = (ticket: Ticket | null, repo: string | null): string | null => {
  if (ticket?.kind === 'tracker') return ticket.key
  if (ticket?.kind !== 'issue') return null
  const owner = ticket.repo ?? repo
  return owner === null ? null : `${owner}#${ticket.number}`
}
