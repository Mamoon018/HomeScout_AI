import { getUserWelcome, resetWelcomeStateForTests } from '@/features/auth/api/authApi'
import { resetRefreshStateForTests } from '@/lib/apiClient'

describe('authApi.getUserWelcome', () => {
  const originalFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = originalFetch
    resetRefreshStateForTests()
    resetWelcomeStateForTests()
  })

  it('gets the same-origin welcome path with credentials included', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ message: 'Welcome Demo User!' }),
    })
    globalThis.fetch = fetchMock

    const result = await getUserWelcome()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/user_welcome',
      expect.objectContaining({
        method: 'GET',
        credentials: 'include',
      }),
    )
    expect(result.ok).toBe(true)
    expect(result.status).toBe(200)
    expect(result.data?.message).toBe('Welcome Demo User!')
  })

  it('refreshes once and retries when the welcome call returns token_expired', async () => {
    let welcomeCalls = 0
    let refreshCalls = 0

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'

      if (url === '/auth/refresh' && method === 'POST') {
        refreshCalls += 1
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ message: 'Session refreshed' }),
        })
      }

      if (url === '/api/user_welcome' && method === 'GET') {
        welcomeCalls += 1
        if (welcomeCalls === 1) {
          return Promise.resolve({
            ok: false,
            status: 401,
            json: async () => ({
              error: 'Not authenticated',
              code: 'token_expired',
            }),
          })
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ message: 'Welcome Demo User!' }),
        })
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url} ${method}`))
    })
    globalThis.fetch = fetchMock as typeof fetch

    const result = await getUserWelcome()

    expect(refreshCalls).toBe(1)
    expect(welcomeCalls).toBe(2)
    expect(result.ok).toBe(true)
    expect(result.status).toBe(200)
    expect(result.data?.message).toBe('Welcome Demo User!')
  })

  it('deduplicates concurrent welcome calls in the same tab', async () => {
    let welcomeCalls = 0

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'

      if (url === '/api/user_welcome' && method === 'GET') {
        welcomeCalls += 1
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ message: 'Welcome Demo User!' }),
        })
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url} ${method}`))
    })
    globalThis.fetch = fetchMock as typeof fetch

    const results = await Promise.all([
      getUserWelcome(),
      getUserWelcome(),
    ])

    expect(welcomeCalls).toBe(1)
    expect(results.every((result) => result.ok)).toBe(true)
  })

  it('returns the original 401 when refresh fails', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'

      if (url === '/auth/refresh' && method === 'POST') {
        return Promise.resolve({
          ok: false,
          status: 401,
          json: async () => ({ error: 'Not authenticated' }),
        })
      }

      if (url === '/api/user_welcome' && method === 'GET') {
        return Promise.resolve({
          ok: false,
          status: 401,
          json: async () => ({
            error: 'Not authenticated',
            code: 'token_expired',
          }),
        })
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url} ${method}`))
    })
    globalThis.fetch = fetchMock as typeof fetch

    const result = await getUserWelcome()

    expect(result.ok).toBe(false)
    expect(result.status).toBe(401)
    expect(result.data).toEqual({
      error: 'Not authenticated',
      code: 'token_expired',
    })
  })
})
