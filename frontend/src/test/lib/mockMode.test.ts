import { isMockMode, resetOnModeChange, warnIfMockIdInLive } from '@/lib/mockMode'

const R1_KEY = 'homescout.r1.runId'
const R2_KEY = 'homescout.r2.run'
const USER_KEY = 'homescout.auth.user'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
  sessionStorage.clear()
})

describe('isMockMode', () => {
  it.each([
    [true, 'true', true],
    [true, undefined, false],
    [true, 'false', false],
    [false, 'true', false],
  ])('DEV=%s, VITE_USE_MOCK_API=%s → %s', (dev, flag, expected) => {
    vi.stubEnv('DEV', dev)
    if (flag !== undefined) vi.stubEnv('VITE_USE_MOCK_API', flag)
    expect(isMockMode()).toBe(expected)
  })
})

describe('resetOnModeChange', () => {
  function seed() {
    sessionStorage.setItem(R1_KEY, 'mock_happy_r1')
    sessionStorage.setItem(R2_KEY, JSON.stringify({ runId: 'mock_happy_r2' }))
    localStorage.setItem(USER_KEY, JSON.stringify({ user_id: 'mock_user', user_name: null }))
  }

  it('clears saved runs and the user when the mode changed since the last load', () => {
    resetOnModeChange(true)
    seed()
    resetOnModeChange(false)
    expect(sessionStorage.getItem(R1_KEY)).toBeNull()
    expect(sessionStorage.getItem(R2_KEY)).toBeNull()
    expect(localStorage.getItem(USER_KEY)).toBeNull()
  })

  it('keeps storage when the mode is the same as last time', () => {
    resetOnModeChange(true)
    seed()
    resetOnModeChange(true)
    expect(sessionStorage.getItem(R1_KEY)).toBe('mock_happy_r1')
  })

  it('treats a first load with no marker as live, so live runs from before are cleared on entering mock', () => {
    sessionStorage.setItem(R1_KEY, '3f2b8c1e-0000-4000-8000-000000000000')
    resetOnModeChange(false)
    expect(sessionStorage.getItem(R1_KEY)).not.toBeNull()
    resetOnModeChange(true)
    expect(sessionStorage.getItem(R1_KEY)).toBeNull()
  })
})

describe('warnIfMockIdInLive', () => {
  it('warns mock_state_mixed for a mock id in live mode', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    warnIfMockIdInLive('/api/amenity-search/runs/mock_happy_r2')
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('[mock_state_mixed]'))
  })

  it('stays quiet for live ids, and for mock ids in mock mode', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    warnIfMockIdInLive('/api/amenity-search/runs/7c4d9e2a-0000-4000-8000-000000000000')
    vi.stubEnv('VITE_USE_MOCK_API', 'true')
    warnIfMockIdInLive('/api/amenity-search/runs/mock_happy_r2')
    expect(warn).not.toHaveBeenCalled()
  })
})
