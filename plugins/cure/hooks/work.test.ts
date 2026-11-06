import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'

const PANE = {
  plugin: 'cure',
  component: 'Pane',
  requestId: 'work',
  props: { title: 'Work', isFocused: false, bodyColumns: 100, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

const SURFACES = ['terminal', 'desktop'] as const
const REFRESH = 120

type World = {
  tracker: string | null
  issues: unknown[]
  prs: Record<string, unknown>[]
  jobs: unknown[]
  clickup: unknown[] | null
  isGhDown: boolean
  ghCalls: number
  clickupReply: unknown
  configGate: Promise<void> | null
  opened: string[]
  closed: string[]
}

const world = (init: Partial<World> = {}): World => ({
  tracker: 'github', issues: [], prs: [], jobs: [], clickup: [], isGhDown: false, ghCalls: 0, clickupReply: undefined, configGate: null, opened: [], closed: [], ...init,
})

const out = (stdout: string, exitCode = 0, stderr = '') =>
  ({ value: { exitCode, stdout, stderr, isStdoutTruncated: false, isStderrTruncated: false } })

const engine = (on: On, w: World) => {
  on('process.run', async (_, e) => {
    const [bin = '', ...args] = [e.argv[0]?.split('/').pop() ?? '', ...e.argv.slice(1)]
    if (bin === 'cure-job' && args[0] === 'config') {
      await w.configGate
      return out(JSON.stringify({ split: { tracker: w.tracker }, dashboard: { 'refresh-seconds': REFRESH } }))
    }
    if (bin === 'cure-job') return out(JSON.stringify(w.jobs))
    if (bin !== 'gh') return out('', 1)
    w.ghCalls++
    if (w.isGhDown) return out('', 1, 'gh: network unreachable')
    if (args[1] === 'issues') return out(JSON.stringify(w.issues))
    if (args[1] === 'prs') return out(JSON.stringify(args.includes('--author') ? w.prs.map(({ headRefName, ...hit }) => hit) : []))
    const pr = w.prs.find(candidate => candidate.number === Number(args[2]))
    return out(JSON.stringify({ headRefName: pr?.headRefName, state: 'OPEN', reviewDecision: '', statusCheckRollup: [] }))
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
  on('tool.list', () => ({ value: [] }))
  on('mcp.call', () => ({
    value: { content: [{ type: 'text', text: w.clickup === null ? 'ClickUp is down' : JSON.stringify(w.clickupReply ?? { tasks: w.clickup }) }], isError: w.clickup === null },
  }))
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
  number, title: `PR ${number}`, url: `https://github.com/${repo}/pull/${number}`, state: 'OPEN', repository: { nameWithOwner: repo }, headRefName,
})

test('a GitHub issue groups the PRs on issue-N-x and issue-N_x branches and the job on its ticket', async ($, on) => {
  const w = world({
    issues: [{ number: 5, title: 'Fix boot', state: 'open', repository: { nameWithOwner: 'o/r' } }],
    prs: [pr(10, 'issue-5-boot'), pr(11, 'issue-5_boot'), pr(12, 'issue-6-other')],
    jobs: [{ id: 'j1', state: 'running', ticket: 'o/r#5', workspace: null }],
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

test('a ClickUp task groups the PR on its RND-833_x branch and the job on its ticket', async ($, on) => {
  const w = world({
    tracker: 'clickup',
    clickup: [{ id: 'abc', custom_id: 'RND-833', name: 'Dashboard', status: 'in progress' }],
    prs: [pr(20, 'RND-833_dashboard'), pr(21, 'main-fix')],
    jobs: [{ id: 'j2', state: 'running', ticket: 'RND-833', workspace: null }, { id: 'j3', state: 'running', ticket: null, workspace: null }],
  })
  await start($, on, w)
  for (const surface of SURFACES) {
    const { found } = await texts(surface, $)
    const at = (text: string) => found.findIndex(line => line.includes(text))
    expect(at('RND-833 Dashboard')).toBeGreaterThanOrEqual(0)
    expect(at('PR 20')).toBeLessThan(at('Unlinked'))
    expect(at('job j2')).toBeLessThan(at('Unlinked'))
    expect(at('PR 21')).toBeGreaterThan(at('Unlinked'))
    expect(at('job j3')).toBeGreaterThan(at('Unlinked'))
  }
})

for (const [name, init] of [
  ['absent', { tracker: null }],
  ['failing', { tracker: 'clickup', clickup: null }],
] as const) {
  test(`a ${name} tracker prints one unavailable line and the PRs and jobs stay in Unlinked`, async ($, on) => {
    const w = world({ ...init, prs: [pr(30, 'RND-1_x')], jobs: [{ id: 'j4', state: 'running', ticket: null, workspace: null }] })
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
  ['a ClickUp URL with a workspace joins the custom id', 'clickup', 'https://app.clickup.com/t/90123/RND-833',
    { id: 'abc', custom_id: 'RND-833', name: 'Dashboard', status: 'open' }, 'RND-833 Dashboard'],
  ['a ClickUp URL with a task id joins the task by its alias', 'clickup', 'https://app.clickup.com/t/abc',
    { id: 'abc', custom_id: 'RND-833', name: 'Dashboard', status: 'open' }, 'RND-833 Dashboard'],
] as const) {
  test(`${name}`, async ($, on) => {
    const w = world({
      tracker, issues: tracker === 'github' ? [task] : [], clickup: tracker === 'clickup' ? [task] : [],
      jobs: [{ id: 'j9', state: 'running', ticket, workspace: null }],
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

test('a ClickUp reply without tasks shows the tasks-unavailable line', async ($, on) => {
  const w = world({ tracker: 'clickup', clickupReply: { error: 'forbidden' } })
  await start($, on, w)
  const { found } = await texts('terminal', $)
  expect(found).toContain('Tasks unavailable: ClickUp: the reply holds no task list')
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
