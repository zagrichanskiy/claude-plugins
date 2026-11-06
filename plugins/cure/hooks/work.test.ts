import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'

import { closeByPerson } from './register'

const PANE = {
  plugin: 'cure',
  component: 'Pane',
  requestId: 'work',
  props: { title: 'Work', isFocused: false, bodyColumns: 100, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

const SURFACES = ['terminal', 'desktop'] as const
const REFRESH = 120
const WORKSPACE = '/ws'
const SUBDIRECTORY = '/ws/sub'

type World = {
  tracker: string | null
  issues: unknown[]
  prs: Record<string, unknown>[]
  jobs: unknown[]
  isGhDown: boolean
  searchExit: number
  ghCalls: number
  mcpReply: unknown
  mcpText: string | null
  mcpIsError: boolean
  mcpCalls: unknown[]
  configGate: Promise<void> | null
  ghGate: Promise<void> | null
  opened: string[]
  closed: string[]
  queries: string[]
  dashboard: Record<string, unknown>
  commands: string[]
}

const world = (init: Partial<World> = {}): World => ({
  tracker: 'github', issues: [], prs: [], jobs: [], isGhDown: false, searchExit: 0, ghCalls: 0, mcpReply: null, mcpText: null, mcpIsError: false, mcpCalls: [], configGate: null, ghGate: null, opened: [], closed: [], queries: [], dashboard: {}, commands: [], ...init,
})

const out = (stdout: string, exitCode = 0, stderr = '') =>
  ({ value: { exitCode, stdout, stderr, isStdoutTruncated: false, isStderrTruncated: false } })

const engine = (on: On, w: World) => {
  on('process.run', async (_, e) => {
    const [bin = '', ...args] = [e.argv[0]?.split('/').pop() ?? '', ...e.argv.slice(1)]
    if (bin === 'cure-job' && args[0] === 'config') {
      await w.configGate
      return out(JSON.stringify({ split: { tracker: w.tracker }, dashboard: { 'refresh-seconds': REFRESH, ...w.dashboard } }))
    }
    if (bin === 'cure-job') return out(JSON.stringify(w.jobs))
    if (bin !== 'gh') return out('', 1)
    w.ghCalls++
    await w.ghGate
    if (w.isGhDown) return out('', 1, 'gh: network unreachable')
    if (args[1] === 'issues') return out(JSON.stringify(w.issues))
    const q = args.find(arg => arg.startsWith('q=')) ?? ''
    w.queries.push(q.slice(2))
    return out(JSON.stringify({ data: { search: { nodes: q.includes('author:@me') ? w.prs : [] } } }), w.searchExit, w.searchExit === 0 ? '' : 'gh: SSO forbidden')
  })
  on('ui.open', (_, e) => {
    w.opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('ui.panes', () => ({ value: w.opened.filter(id => !w.closed.includes(id)).map(id => ({ id, title: id, isPlaced: true, isShown: true, isFocused: false })) }))
  on('ui.close', (_, e) => {
    w.closed.push(e.id)
    return { value: undefined }
  })
  on('session.cwd', () => ({ value: SUBDIRECTORY }))
  on('session.root', () => ({ value: WORKSPACE }))
  on('command.register', (_, e) => {
    w.commands.push(e.name)
    return { value: { command: e.name } }
  })
  on('mcp.call', (_, e) => {
    w.mcpCalls.push(e)
    return { value: { content: [{ type: 'text', text: w.mcpText ?? JSON.stringify(w.mcpReply) }], isError: w.mcpIsError } }
  })
  on('classic.SessionStart', () => ({}))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
}

const start = async ($: Engine, on: On, w: World, env: Record<string, string> = {},
  isDispatcher = false, isInteractive = true, isSessionFirst = false) => {
  const clock = mock.clock(on, { now: 1_000_000 })
  mock.env(on, env)
  engine(on, w)
  const classic = () => $.classic.SessionStart({ source: 'startup', agent_type: isDispatcher ? 'cure:dispatcher' : 'main' })
  const session = () => $.session.start({ cwd: '/', surface: 'terminal', isInteractive })
  if (isSessionFirst) await session()
  else await classic()
  await (isSessionFirst ? classic : session)()
  await clock.settle()
  return clock
}

const texts = async (surface: (typeof SURFACES)[number], $: Engine) => {
  const ui = await $.ui.mount({ ...PANE, surface })
  const found = (await ui.findAll({ type: 'Text' })).map(text => text.text)
  const hrefs = (await ui.findAll({ type: 'Link' })).map(link => link.props.href)
  await ui.unmount()
  return { found, hrefs }
}

const pr = (number: number, headRefName: string, repo = 'o/r') => ({
  number, title: `PR ${number}`, url: `https://github.com/${repo}/pull/${number}`, state: 'OPEN', repository: { nameWithOwner: repo }, headRefName, reviewDecision: null, commits: { nodes: [] },
})

test('a GitHub issue groups the PRs on issue-N-x and issue-N_x branches and the job on its ticket', async ($, on) => {
  const w = world({
    issues: [{ number: 5, title: 'Fix boot', state: 'open', repository: { nameWithOwner: 'o/r' } }],
    prs: [pr(10, 'issue-5-boot'), pr(11, 'issue-5_boot'), pr(12, 'issue-6-other')],
    jobs: [{ id: 'j1', state: 'running', ticket: 'o/r#5', workspace: WORKSPACE }],
  })
  await start($, on, w)
  for (const surface of SURFACES) {
    const { found } = await texts(surface, $)
    const at = (text: string) => found.findIndex(line => line.includes(text))
    expect(at('o/r#5 Fix boot')).toBeGreaterThanOrEqual(0)
    expect(at('Unlinked')).toBeGreaterThan(at('o/r#5 Fix boot'))
    expect(at('PR 10')).toBeGreaterThan(at('o/r#5 Fix boot'))
    expect(at('PR 11')).toBeLessThan(at('Unlinked'))
    expect(at('job j1 running')).toBeLessThan(at('Unlinked'))
    expect(at('PR 12')).toBeGreaterThan(at('Unlinked'))
  }
})

const TASKS_MCP = {
  'tasks-mcp-server': 'acme-tasks', 'tasks-mcp-tool': 'list_items', 'tasks-mcp-args': { mine: true },
  'tasks-field-items': 'data.items', 'tasks-field-key': 'ref', 'tasks-field-title': 'name',
  'tasks-field-status': 'state.label', 'tasks-field-url': 'link',
}

test('a configured MCP tool lists the tasks by the configured fields and joins PRs and jobs by key and URL', async ($, on) => {
  const w = world({
    tracker: 'acme', dashboard: TASKS_MCP,
    mcpReply: { data: { items: [{ ref: 'ACME-7', name: 'Dashboard', state: { label: 'doing' }, link: 'https://tasks.example/i/7' }] } },
    prs: [pr(20, 'ACME-7_dashboard'), pr(21, 'main-fix')],
    jobs: [
      { id: 'j2', state: 'running', ticket: 'ACME-7', workspace: WORKSPACE },
      { id: 'j5', state: 'running', ticket: 'https://tasks.example/i/7', workspace: WORKSPACE },
      { id: 'j3', state: 'running', ticket: null, workspace: WORKSPACE },
    ],
  })
  await start($, on, w)
  expect(w.mcpCalls[0]).toMatchObject({ server: 'acme-tasks', tool: 'list_items', args: { mine: true } })
  for (const surface of SURFACES) {
    const { found } = await texts(surface, $)
    const at = (text: string) => found.findIndex(line => line.includes(text))
    expect(at('ACME-7 Dashboard')).toBeGreaterThanOrEqual(0)
    expect(at('PR 20')).toBeLessThan(at('Unlinked'))
    expect(at('job j2')).toBeLessThan(at('Unlinked'))
    expect(at('job j5')).toBeLessThan(at('Unlinked'))
    expect(at('PR 21')).toBeGreaterThan(at('Unlinked'))
    expect(at('job j3')).toBeGreaterThan(at('Unlinked'))
  }
})

test('a non-github tracker without the MCP task keys shows the tasks-unavailable line', async ($, on) => {
  const w = world({ tracker: 'acme' })
  await start($, on, w)
  const { found } = await texts('terminal', $)
  expect(found.filter(line => line.startsWith('Tasks unavailable: split.tracker acme has no task source'))).toHaveLength(1)
  expect(w.mcpCalls).toHaveLength(0)
})

for (const [name, init] of [
  ['absent', { tracker: null }],
  ['failing', { tracker: 'acme', dashboard: TASKS_MCP, mcpReply: { error: 'forbidden' } }],
] as const) {
  test(`a ${name} tracker prints one unavailable line and the PRs and jobs stay in Unlinked`, async ($, on) => {
    const w = world({ ...init, prs: [pr(30, 'ACME-1_x')], jobs: [{ id: 'j4', state: 'running', ticket: null, workspace: WORKSPACE }] })
    await start($, on, w)
    for (const surface of SURFACES) {
      const { found } = await texts(surface, $)
      expect(found.filter(line => line.startsWith('Tasks '))).toHaveLength(1)
      expect(found.some(line => line.includes('PR 30'))).toBe(true)
      expect(found.some(line => line.includes('job j4'))).toBe(true)
      expect(found.some(line => line === 'Unlinked')).toBe(true)
    }
  })
}

for (const [name, init, reason] of [
  ['an MCP error reply', { mcpIsError: true, mcpText: 'forbidden: token expired\nretry later' }, 'forbidden: token expired'],
  ['a non-JSON MCP reply', { mcpText: 'Here are your items' }, 'the reply is not JSON'],
] as const) {
  test(`${name} prints one tasks-unavailable line naming the server and tool`, async ($, on) => {
    const w = world({ tracker: 'acme', dashboard: TASKS_MCP, ...init })
    await start($, on, w)
    const { found } = await texts('terminal', $)
    expect(found.filter(line => line.startsWith('Tasks '))).toEqual([`Tasks unavailable: acme-tasks list_items: ${reason}`])
  })
}

test('an empty tasks-field-items reads a top-level list, skips an item without a key and shows a numeric key', async ($, on) => {
  const w = world({
    tracker: 'acme', dashboard: { ...TASKS_MCP, 'tasks-field-items': '' },
    mcpReply: [{ ref: 'ACME-8', name: 'Keyed' }, { name: 'Unkeyed' }, { ref: 42, name: 'Numbered' }],
  })
  await start($, on, w)
  const { found } = await texts('terminal', $)
  expect(found.some(line => line.includes('ACME-8 Keyed'))).toBe(true)
  expect(found.some(line => line.includes('42 Numbered'))).toBe(true)
  expect(found.some(line => line.includes('Unkeyed'))).toBe(false)
  expect(found.some(line => line.startsWith('Tasks '))).toBe(false)
})

test('each role searches open PRs with one user qualifier per configured owner', async ($, on) => {
  const w = world({ dashboard: { 'github-owners': ['acme', 'o2'] } })
  await start($, on, w)
  expect(w.queries).toEqual([
    'is:pr is:open author:@me user:acme user:o2',
    'is:pr is:open review-requested:@me user:acme user:o2',
  ])
})

test('the PR searches carry no user qualifier when no owner is configured', async ($, on) => {
  const w = world()
  await start($, on, w)
  expect(w.queries).toEqual(['is:pr is:open author:@me', 'is:pr is:open review-requested:@me'])
})

const job = (id: string, state: string, workspace: string | null = WORKSPACE) => ({ id, state, ticket: null, workspace })

test('the jobs list holds the jobs in a configured state, so a done job is hidden and a failed job shown', async ($, on) => {
  const w = world({ jobs: [job('jdone', 'done'), job('jfailed', 'failed')] })
  await start($, on, w)
  const { found } = await texts('terminal', $)
  expect(found.some(line => line.includes('job jfailed'))).toBe(true)
  expect(found.some(line => line.includes('job jdone'))).toBe(false)
})

test('dashboard.job-states replaces the default states', async ($, on) => {
  const w = world({ dashboard: { 'job-states': ['done'] }, jobs: [job('jdone', 'done'), job('jrun', 'running')] })
  await start($, on, w)
  const { found } = await texts('terminal', $)
  expect(found.some(line => line.includes('job jdone'))).toBe(true)
  expect(found.some(line => line.includes('job jrun'))).toBe(false)
})

for (const [scope, isShown] of [['workspace', false], ['all', true]] as const) {
  test(`under job-scope ${scope} a job of another workspace is ${isShown ? 'shown' : 'hidden'}`, async ($, on) => {
    const w = world({
      dashboard: { 'job-scope': scope },
      jobs: [job('jhere', 'running'), job('jaway', 'running', '/elsewhere'), job('jnone', 'running', null)],
    })
    await start($, on, w)
    const { found } = await texts('terminal', $)
    const has = (id: string) => found.some(line => line.includes(`job ${id}`))
    expect(has('jhere')).toBe(true)
    expect(has('jaway')).toBe(isShown)
    expect(has('jnone')).toBe(isShown)
  })
}

test('a failed GraphQL search keeps the last good PRs and marks them stale', async ($, on) => {
  const w = world({ prs: [pr(41, 'feature')] })
  const clock = await start($, on, w)
  w.isGhDown = true
  await clock.advance(REFRESH * 1000)
  const { found } = await texts('terminal', $)
  expect(found.some(line => line.startsWith('PRs as of'))).toBe(true)
  expect(found.some(line => line.includes('PR 41'))).toBe(true)
})

test('a GraphQL reply without search nodes fails the PR source', async ($, on) => {
  const w = world({ prs: [pr(42, 'feature')] })
  const clock = await start($, on, w)
  w.prs = null as never
  await clock.advance(REFRESH * 1000)
  const { found } = await texts('terminal', $)
  expect(found.some(line => line.startsWith('PRs as of') && line.includes('no search result'))).toBe(true)
  expect(found.some(line => line.includes('PR 42'))).toBe(true)
})

test('a GraphQL reply with a non-zero exit but usable nodes shows those PRs as fresh', async ($, on) => {
  const w = world({ prs: [pr(43, 'feature')], searchExit: 1 })
  await start($, on, w)
  const { found } = await texts('terminal', $)
  expect(found.some(line => line.includes('PR 43'))).toBe(true)
  expect(found.some(line => line.startsWith('PRs as of'))).toBe(false)
  expect(found).toContain('PRs incomplete: gh: SSO forbidden')
})

test('a null node and a node without repository are skipped while the other PRs show', async ($, on) => {
  const w = world({ prs: [null, { ...pr(44, 'feature'), repository: undefined }, pr(45, 'feature')] })
  await start($, on, w)
  const { found } = await texts('terminal', $)
  expect(found.some(line => line.includes('PR 45'))).toBe(true)
  expect(found.some(line => line.includes('PR 44'))).toBe(false)
  expect(found.some(line => line.startsWith('PRs as of'))).toBe(false)
})

test('a failed refresh keeps the last good data and says how old it is', async ($, on) => {
  const w = world({ prs: [pr(40, 'feature')] })
  const clock = await start($, on, w)
  w.isGhDown = true
  await clock.advance(REFRESH * 1000)
  for (const surface of SURFACES) {
    const { found } = await texts(surface, $)
    expect(found).toContain('PRs as of 2 min ago: gh: network unreachable')
    expect(found.some(line => line.includes('PR 40'))).toBe(true)
  }
})

for (const [name, env, isDispatcher, isInteractive, isOpened] of [
  ['an interactive user session', {}, false, true, true],
  ['a job session', { CURE_JOB_ID: 'j1' }, false, true, false],
  ['the dispatcher', {}, true, true, false],
  ['a non-interactive session', {}, false, false, false],
] as const) {
  test(`${name} ${isOpened ? 'opens' : 'does not open'} the work pane`, async ($, on) => {
    const w = world()
    await start($, on, w, env, isDispatcher, isInteractive)
    expect(w.opened).toEqual(isOpened ? ['work'] : [])
  })
}

test('a dispatcher whose session.start fires first never opens the pane or calls gh', async ($, on) => {
  const w = world()
  await start($, on, w, {}, true, true, true)
  expect(w.opened).toEqual([])
  expect(w.ghCalls).toBe(0)
})

test('a user session waits for both start hooks, whichever fires first, then opens the pane once', async ($, on) => {
  const w = world()
  const clock = mock.clock(on, { now: 1_000_000 })
  mock.env(on, {})
  engine(on, w)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.settle()
  expect(w.opened).toEqual([])
  expect(w.ghCalls).toBe(0)
  await $.classic.SessionStart({ source: 'startup', agent_type: 'main' })
  await clock.settle()
  expect(w.opened).toEqual(['work'])
  expect(w.ghCalls).toBeGreaterThan(0)
})

const taskLine = (found: string[], text: string) => found.findIndex(line => line.includes(text))

for (const [name, tracker, ticket, task, key] of [
  ['a GitHub issue URL joins owner/repo#N', 'github', 'https://github.com/o/r/issues/5',
    { number: 5, title: 'Fix boot', state: 'open', repository: { nameWithOwner: 'o/r' } }, 'o/r#5 Fix boot'],
] as const) {
  test(`${name}`, async ($, on) => {
    const w = world({
      tracker, issues: [task],
      jobs: [{ id: 'j9', state: 'running', ticket, workspace: WORKSPACE }],
    })
    await start($, on, w)
    const { found } = await texts('terminal', $)
    expect(taskLine(found, key)).toBeGreaterThanOrEqual(0)
    expect(taskLine(found, 'job j9')).toBeGreaterThan(taskLine(found, key))
    expect(found).not.toContain('Unlinked')
  })
}

test('a refresh that throws settles every source as failed instead of fetching forever', async ($, on) => {
  const w = world()
  mock.env(on, {})
  engine(on, w)
  on('clock.now', () => {
    throw new Error('clock unreadable')
  })
  on('clock.every', () => ({ value: undefined }))
  on('ui.log', () => ({ value: undefined }))
  const written: unknown[] = []
  on('state.set', (_, e, next) => {
    if (e.key === 'work') written.push(e.value)
    return next(e)
  })
  await $.classic.SessionStart({ source: 'startup', agent_type: 'main' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  for (let turn = 0; turn < 200; turn++) await Promise.resolve()
  const failed = { kind: 'unavailable' }
  expect(written[0]).toMatchObject({ value: { tasks: failed, prs: failed, jobs: failed, checkedAt: 0 } })
})

test('session start returns without waiting on the config read', async ($, on) => {
  let release = () => {}
  const w = world({ configGate: new Promise<void>(resolve => (release = resolve)) })
  const clock = mock.clock(on, { now: 1_000_000 })
  mock.env(on, {})
  engine(on, w)
  await $.classic.SessionStart({ source: 'startup', agent_type: 'main' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(w.opened).toEqual([])
  release()
  await clock.settle()
  expect(w.opened).toEqual(['work'])
})

const runWork = ($: Engine) =>
  $.command.run({ command: 'cure-work', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 } })

test('session start registers the cure-work command', async ($, on) => {
  const w = world()
  await start($, on, w)
  expect(w.commands).toEqual(['cure-work'])
})

test('the cure-work command in a user session reopens a closed pane and restarts polling', async ($, on) => {
  const w = world()
  const clock = await start($, on, w)
  w.closed.push('work')
  const calls = w.ghCalls
  const { text } = await runWork($)
  await clock.settle()
  expect(text).toBe('Work pane opened.')
  expect(w.opened).toEqual(['work', 'work'])
  expect(w.ghCalls).toBeGreaterThan(calls)
})

for (const [name, env, isDispatcher] of [
  ['a job session', { CURE_JOB_ID: 'j1' }, false],
  ['the dispatcher', {}, true],
] as const) {
  test(`the cure-work command in ${name} answers that the pane is not available and opens nothing`, async ($, on) => {
    const w = world()
    const clock = await start($, on, w, env, isDispatcher)
    const { text } = await runWork($)
    await clock.settle()
    expect(text).toContain('only in an interactive user session')
    expect(w.opened).toEqual([])
    expect(w.ghCalls).toBe(0)
  })
}

test('the cure-work command while the pane is open restarts polling with a newly read config', async ($, on) => {
  const w = world()
  const clock = await start($, on, w)
  w.dashboard = { 'refresh-seconds': 30 }
  await runWork($)
  await clock.settle()
  const calls = w.ghCalls
  await clock.advance(30_000)
  expect(w.ghCalls).toBeGreaterThan(calls)
})

const seedClosed = (on: On) => {
  const mark = { value: true as unknown, version: 1 }
  on('state.get', (_, e, next) => (e.key === 'isWorkClosed' ? { value: { ...mark } } : next(e)))
  on('state.set', (_, e, next) => {
    if (e.key !== 'isWorkClosed') return next(e)
    mark.value = e.value
    mark.version++
    return { value: { isSet: true, version: mark.version } }
  })
  return mark
}

test('a session start does not open or poll while a person has closed the pane', async ($, on) => {
  const w = world()
  const clock = mock.clock(on, { now: 1_000_000 })
  mock.env(on, {})
  engine(on, w)
  seedClosed(on)
  await $.classic.SessionStart({ source: 'clear', agent_type: 'main' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.settle()
  expect(w.opened).toEqual([])
  expect(w.ghCalls).toBe(0)
})

test('the cure-work command opens the pane a person closed, clears the closed mark and polls', async ($, on) => {
  const w = world()
  const clock = mock.clock(on, { now: 1_000_000 })
  mock.env(on, {})
  engine(on, w)
  const mark = seedClosed(on)
  await $.classic.SessionStart({ source: 'startup', agent_type: 'main' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.settle()
  await runWork($)
  await clock.settle()
  expect(w.opened).toEqual(['work'])
  expect(w.ghCalls).toBeGreaterThan(0)
  expect(mark.value).toBe(false)
})

const person = ($: Engine, mark: { value: unknown; version: number }) => ({
  ...$,
  ui: { log: (text: string) => { throw new Error(text) } },
  state: {
    get: async () => ({ ...mark }),
    set: async (_: unknown, value: unknown) => ({ isSet: true, version: ++mark.version, value: (mark.value = value) }),
  },
}) as never

test('a person close writes the closed mark, so a later start opens nothing and cure-work reopens', async ($, on) => {
  const w = world()
  const clock = mock.clock(on, { now: 1_000_000 })
  mock.env(on, {})
  engine(on, w)
  const mark = seedClosed(on)
  mark.value = false
  await closeByPerson(person($, mark))
  expect(mark.value).toBe(true)
  await $.classic.SessionStart({ source: 'clear', agent_type: 'main' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.advance(REFRESH * 2000)
  expect(w.opened).toEqual([])
  expect(w.ghCalls).toBe(0)
  await runWork($)
  await clock.settle()
  expect(w.opened).toEqual(['work'])
  expect(w.ghCalls).toBeGreaterThan(0)
  expect(mark.value).toBe(false)
})

test('a cure-work restart during a running refresh runs one more fetch with the new config, and a tick is dropped', async ($, on) => {
  const w = world()
  let release = () => {}
  const clock = mock.clock(on, { now: 1_000_000 })
  mock.env(on, {})
  engine(on, w)
  await $.classic.SessionStart({ source: 'startup', agent_type: 'main' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await clock.settle()
  w.ghGate = new Promise<void>(resolve => (release = resolve))
  w.queries.length = 0
  await clock.advance(REFRESH * 1000)
  await clock.advance(REFRESH * 1000)
  w.dashboard = { 'refresh-seconds': 30, 'github-owners': ['newowner'] }
  await runWork($)
  release()
  await clock.settle()
  expect(w.queries.filter(q => q.includes('user:newowner'))).toHaveLength(2)
  expect(w.queries.filter(q => !q.includes('user:newowner')).length).toBeLessThanOrEqual(2)
})
