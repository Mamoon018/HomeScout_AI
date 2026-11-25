import { POLL_CAP, SLOW_R1_WORK_MS, SLOW_R2_RUN_MS, createRunStore } from '@/mocks/mockRunStore'

type Body = { status?: string; run_id?: string; retryable?: boolean; completed_step?: string; result?: unknown }
const body = (reply: { body: unknown }) => reply.body as Body
const status = (reply: { body: unknown }) => body(reply).status

describe('mock run store', () => {
  beforeEach(() => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.spyOn(console, 'info').mockImplementation(() => {})
  })
  afterEach(() => vi.restoreAllMocks())

  it('happy R1: running, needs_answers, then running and finished after the answers', () => {
    const store = createRunStore()
    const started = store.start('happy', 'r1')
    expect(started.status).toBe(200)
    expect(body(started).run_id).toBe('mock_happy_r1')
    expect(status(started)).toBe('running')
    expect(status(store.read('mock_happy_r1', 'r1'))).toBe('running')
    expect(status(store.read('mock_happy_r1', 'r1'))).toBe('needs_answers')
    expect(status(store.answer('mock_happy_r1'))).toBe('running')
    expect(status(store.read('mock_happy_r1', 'r1'))).toBe('running')
    expect(status(store.read('mock_happy_r1', 'r1'))).toBe('finished')
  })

  it('happy R2: 202 running, a progress step, then finished with places', () => {
    const store = createRunStore()
    const started = store.start('happy', 'r2')
    expect(started.status).toBe(202)
    expect(status(store.read('mock_happy_r2', 'r2'))).toBe('running')
    expect(body(store.read('mock_happy_r2', 'r2')).completed_step).toBe('discovery')
    const done = store.read('mock_happy_r2', 'r2')
    expect(status(done)).toBe('finished')
    expect(body(done).result).not.toEqual({})
  })

  it('error: fails with Retry left, then finishes after the retry', () => {
    const store = createRunStore()
    store.start('error', 'r3')
    store.read('mock_error_r3', 'r3')
    const failed = store.read('mock_error_r3', 'r3')
    expect(body(failed)).toMatchObject({ status: 'failed', retryable: true })
    expect(store.retry('mock_error_r3', 'r3').status).toBe(202)
    store.read('mock_error_r3', 'r3')
    expect(status(store.read('mock_error_r3', 'r3'))).toBe('finished')
  })

  it('paused: R1 holds at needs_answers until answered; R2 holds at running', () => {
    const store = createRunStore()
    expect(status(store.start('paused', 'r1'))).toBe('needs_answers')
    expect(status(store.read('mock_paused_r1', 'r1'))).toBe('needs_answers')
    expect(status(store.answer('mock_paused_r1'))).toBe('finished')
    store.start('paused', 'r2')
    for (let i = 0; i < 5; i++) expect(status(store.read('mock_paused_r2', 'r2'))).toBe('running')
  })

  it('empty: R2 and R3 finish with no results', () => {
    const store = createRunStore()
    store.start('empty', 'r2')
    for (let i = 0; i < 2; i++) store.read('mock_empty_r2', 'r2')
    expect(body(store.read('mock_empty_r2', 'r2')).result).toEqual({})
    store.start('empty', 'r3')
    for (let i = 0; i < 2; i++) store.read('mock_empty_r3', 'r3')
    expect(body(store.read('mock_empty_r3', 'r3')).result).toEqual([])
  })

  it('not-found and unauthenticated answer 404 and 401 token_expired', () => {
    const store = createRunStore()
    expect(store.read('mock_not-found_r1', 'r1').status).toBe(404)
    expect(store.start('unauthenticated', 'r2')).toMatchObject({ status: 401, body: { code: 'token_expired' } })
    expect(store.read('mock_unauthenticated_r3', 'r3').status).toBe(401)
  })

  it('slow: R1 work calls are delayed and R2 runs past its 120 s notice', () => {
    let now = 0
    const store = createRunStore(() => now)
    expect(store.start('slow', 'r1').delayMs).toBe(SLOW_R1_WORK_MS)
    store.start('slow', 'r2')
    for (let i = 0; i < 5; i++) expect(status(store.read('mock_slow_r2', 'r2'))).toBe('running')
    now = SLOW_R2_RUN_MS + 1
    expect(status(store.read('mock_slow_r2', 'r2'))).toBe('finished')
  })

  it('reports a run still running after the poll cap as failed, mock_state_stuck', () => {
    const store = createRunStore()
    store.start('running', 'r2')
    for (let i = 0; i < POLL_CAP; i++) expect(status(store.read('mock_running_r2', 'r2'))).toBe('running')
    expect(body(store.read('mock_running_r2', 'r2'))).toMatchObject({ status: 'failed', retryable: false })
    expect(console.warn).toHaveBeenCalledWith(expect.stringContaining('[mock_state_stuck]'))
  })

  it('an unseen id answers its end state, and a child settles its parents', () => {
    const store = createRunStore()
    expect(status(store.read('mock_happy_r3', 'r3'))).toBe('finished')
    // In error, an unseen run ends failed, but a parent of a run that exists has finished.
    expect(status(store.read('mock_error_r3', 'r3'))).toBe('failed')
    expect(status(store.read('mock_error_r2', 'r2'))).toBe('finished')
    expect(status(store.read('mock_error_r1', 'r1'))).toBe('finished')
  })

  it('links the chain through the fixed ids', () => {
    const store = createRunStore()
    expect(store.read('mock_happy_r3', 'r3').body).toMatchObject({ r2_run_id: 'mock_happy_r2' })
    expect(store.read('mock_happy_r2', 'r2').body).toMatchObject({ r1_run_id: 'mock_happy_r1' })
  })

  it('answers 404 with mock_unknown_scenario for an id outside the table or the wrong stage', () => {
    const store = createRunStore()
    expect(store.read('3f2b8c1e-0000-4000-8000-000000000000', 'r1').status).toBe(404)
    expect(store.read('mock_happy_r2', 'r1').status).toBe(404)
    expect(console.warn).toHaveBeenCalledWith(expect.stringContaining('[mock_unknown_scenario]'))
  })
})
