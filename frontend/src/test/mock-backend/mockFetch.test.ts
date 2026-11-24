import { getUserWelcome, login } from '@/features/auth/api/authApi'
import { getRun, startRun, submitAnswers } from '@/features/r1-interpretation/api/r1Api'
import { getR2Run, startR2Run } from '@/features/r2-proximity/api/r2Api'
import { getR3Run, startR3Run } from '@/features/places-metrics/api/r3Api'
import { installMockFetch } from '@/mocks/mockFetch'
import type { Scenario } from '@/mocks/mockScenario'

/** The real fetch stand-in, so pass-through can be seen without the network. */
const realFetch = vi.fn(async () => new Response('{"passed":true}', { status: 200 }))
let uninstall: () => void

function install(scenario: Scenario) {
  uninstall = installMockFetch({ scenario, delayMs: 0, banner: false })
}

beforeEach(() => {
  vi.stubGlobal('fetch', realFetch)
  realFetch.mockClear()
})
afterEach(() => {
  uninstall?.()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('mock fetch', () => {
  it('answers sign-in and the welcome call without a backend', async () => {
    install('happy')
    const signedIn = await login({ email: 'dev@example.test', password: 'x' })
    expect(signedIn).toMatchObject({ ok: true, data: { user_id: 'mock_user' } })
    const welcome = await getUserWelcome()
    expect(welcome.data?.message).toContain('Mock Renter')
    expect(realFetch).not.toHaveBeenCalled()
  })

  it('plays a full R1 run through the real r1Api', async () => {
    install('happy')
    const started = await startRun('a brief')
    expect(started).toMatchObject({ ok: true, view: { runId: 'mock_happy_r1', status: 'running' } })
    await getRun('mock_happy_r1')
    const paused = await getRun('mock_happy_r1')
    expect(paused.ok && paused.view.status).toBe('needs_answers')
    expect(paused.ok && paused.view.questions.length).toBeGreaterThan(0)
    await submitAnswers('mock_happy_r1', [{ category_id: 7, option: 1 }])
    await getRun('mock_happy_r1')
    const done = await getRun('mock_happy_r1')
    expect(done.ok && done.view.plan?.length).toBeGreaterThan(0)
  })

  it('starts R2 and R3 from the ids the earlier stage handed out', async () => {
    install('happy')
    const r2 = await startR2Run({ r1RunId: 'mock_happy_r1', latitude: 48.1, longitude: 11.5, radiusKm: 2 })
    expect(r2).toMatchObject({ ok: true, view: { runId: 'mock_happy_r2', status: 'running' } })
    const r3 = await startR3Run('mock_happy_r2')
    expect(r3).toMatchObject({ ok: true, view: { runId: 'mock_happy_r3', r2RunId: 'mock_happy_r2' } })
    const parent = await getR2Run('mock_happy_r2')
    expect(parent.ok && parent.view.status).toBe('finished')
  })

  it('sends 401 through the real refresh path in the unauthenticated scenario', async () => {
    install('unauthenticated')
    const result = await getR3Run('mock_unauthenticated_r3')
    expect(result).toEqual({ ok: false, error: { kind: 'unauthenticated' } })
  })

  it('passes non-backend requests to the real fetch untouched', async () => {
    install('happy')
    const res = await window.fetch('https://project.supabase.co/auth/v1/signup', { method: 'POST' })
    expect(await res.json()).toEqual({ passed: true })
    expect(realFetch).toHaveBeenCalledTimes(1)
  })

  it('answers an unknown /api route with 501 mock_unhandled_route, never the real backend', async () => {
    install('happy')
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    const res = await window.fetch('/api/not-a-route')
    expect(res.status).toBe(501)
    expect(await res.json()).toMatchObject({ code: 'mock_unhandled_route' })
    expect(error).toHaveBeenCalledWith(expect.stringContaining('GET /api/not-a-route'))
    expect(realFetch).not.toHaveBeenCalled()
  })

  it('rejects with AbortError when the caller aborts during the reply delay', async () => {
    uninstall = installMockFetch({ scenario: 'happy', delayMs: 10_000, banner: false })
    const controller = new AbortController()
    const pending = window.fetch('/api/user_welcome', { signal: controller.signal })
    controller.abort()
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('restores the real fetch on uninstall', async () => {
    install('happy')
    uninstall()
    await window.fetch('/api/user_welcome')
    expect(realFetch).toHaveBeenCalledTimes(1)
  })
})
