import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

const BAND = {
  plugin: 'cure',
  component: 'AbovePrompt',
  requestId: 'band',
  props: { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 100, scroll: { offset: 0, bodyRows: 10 }, view: {} },
} as const

const SURFACES = ['terminal', 'desktop'] as const

const JOB = {
  id: 'j1', state: 'running', open: 0, ticket: 'ABC-12', 'ticket-summary': 'Fix the boot loop',
  prs: ['https://github.com/o/r/pull/7'], branch: 'fix-boot' as string | null, workspace: '/src/r',
}

const engine = (on: On, job: Partial<typeof JOB>, calls: string[][] = [], prompts: string[] = []) => {
  on('process.run', (_, e) => {
    const argv = [e.argv[0]?.split('/').pop() ?? '', ...e.argv.slice(1)]
    calls.push(argv)
    const stdout = argv.includes('list') ? JSON.stringify([{ ...JOB, ...job }])
      : argv.includes('config') ? '"https://jira.example.com"'
      : argv.includes('remote') ? 'git@github.com:o/r.git\n'
      : argv.includes('--show-current') ? 'wt-branch\n' : ''
    return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('session.cwd', () => ({ value: '/wt/j1' }))
  on('prompt.submit', (_, e) => {
    prompts.push(e.text)
    return { text: e.text }
  })
}

test('a job session draws its ticket, PR, branch and worktree', async ($, on) => {
  mock.env(on, { CURE_JOB_ID: 'j1' })
  engine(on, {})
  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ ...BAND, surface })
    const links = await ui.findAll({ type: 'Link' })
    expect(links.map(link => link.props.href)).toEqual(['https://jira.example.com/browse/ABC-12', JOB.prs[0]])
    expect(await ui.find({ type: 'Text', text: 'Fix the boot loop' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'fix-boot /wt/j1' })).toBeDefined()
    expect(await ui.findAll({ type: 'Button' })).toEqual([])
    await ui.unmount()
  }
})

for (const [ticket, href] of [
  ['o2/r2#5', 'https://github.com/o2/r2/issues/5'],
  ['#5', 'https://github.com/o/r/issues/5'],
  ['https://tracker.example.com/5', 'https://tracker.example.com/5'],
] as const) {
  test(`ticket ${ticket} links to ${href}; the branch falls back to the worktree's`, async ($, on) => {
    mock.env(on, { CURE_JOB_ID: 'j1' })
    engine(on, { ticket, prs: [], branch: null })
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ ...BAND, surface })
      expect((await ui.findAll({ type: 'Link' })).map(link => link.props.href)).toEqual([href])
      expect(await ui.find({ type: 'Text', text: 'wt-branch /wt/j1' })).toBeDefined()
      await ui.unmount()
    }
  })
}

for (const [name, env, isDispatcher] of [
  ['the dispatcher with no job awaiting approval', {}, true],
  ['a job session whose job is not listed', { CURE_JOB_ID: 'j9' }, false],
] as const) {
  test(`${name} draws only the engine's band`, async ($, on) => {
    mock.env(on, env)
    engine(on, {})
    on('ui.render', ($, e) => $.ui.resolve(e).Text({ children: 'engine' }))
    on('classic.SessionStart', () => ({}))
    if (isDispatcher) await $.classic.SessionStart({ source: 'startup', agent_type: 'cure:dispatcher' })
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ ...BAND, surface })
      expect((await ui.findAll({ type: 'Text' })).map(text => text.text)).toEqual(['engine'])
      await ui.unmount()
    }
  })
}

test('the dispatcher approves or rejects a job awaiting approval and wakes itself', async ($, on) => {
  mock.env(on, { CURE_JOB_ID: 'j1' })
  const calls: string[][] = []
  const prompts: string[] = []
  engine(on, { state: 'awaiting-approval' }, calls, prompts)
  on('classic.SessionStart', () => ({}))
  await $.classic.SessionStart({ source: 'startup', agent_type: 'cure:dispatcher' })
  for (const surface of SURFACES) {
    calls.length = prompts.length = 0
    const ui = await $.ui.mount({ ...BAND, surface })
    await ui.press({ key: 'approve-j1' })
    expect(calls).toContainEqual(['cure-job', 'approve', 'j1', '--by', 'user'])
    await ui.press({ key: 'reject-j1' })
    expect(calls).toContainEqual(['cure-job', 'close', 'j1'])
    expect(prompts).toEqual(['Approved job j1 from the band; rescan.', 'Rejected job j1 from the band; rescan.'])
    await ui.unmount()
  }
})

test('the dispatcher offers no Approve for a job with open items', async ($, on) => {
  mock.env(on, {})
  engine(on, { state: 'awaiting-approval', open: 2 })
  on('classic.SessionStart', () => ({}))
  await $.classic.SessionStart({ source: 'startup', agent_type: 'cure:dispatcher' })
  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect((await ui.findAll({ type: 'Button' })).map(button => button.props.label)).toEqual(['Reject'])
    await ui.unmount()
  }
})
