import { getUserWelcome, resetWelcomeStateForTests } from '@/features/auth/api/authApi'
import { apiFetch, ensureRefreshed, resetRefreshStateForTests } from '@/lib/apiClient'

describe('apiClient refresh deduplication', () => {
  const originalFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = originalFetch
    resetRefreshStateForTests()
    resetWelcomeStateForTests()
  })

  it('deduplicates concurrent refresh calls and retries protected requests', async () => {
    let refreshCalls = 0
    let welcomeCalls = 0

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

    const results = await Promise.all([
      getUserWelcome(),
      getUserWelcome(),
      getUserWelcome(),
    ])

    expect(refreshCalls).toBe(1)
    expect(welcomeCalls).toBe(2)
    expect(results.every((result) => result.ok && result.status === 200)).toBe(true)
    expect(results.every((result) => result.data?.message === 'Welcome Demo User!')).toBe(
      true,
    )
  })

  it('shares one refresh promise across concurrent ensureRefreshed calls', async () => {
    let refreshCalls = 0

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/auth/refresh') {
        refreshCalls += 1
        return new Promise((resolve) => {
          setTimeout(() => {
            resolve({
              ok: true,
              status: 200,
              json: async () => ({ message: 'Session refreshed' }),
            })
          }, 50)
        })
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`))
    })
    globalThis.fetch = fetchMock as typeof fetch

    const [first, second] = await Promise.all([ensureRefreshed(), ensureRefreshed()])

    expect(refreshCalls).toBe(1)
    expect(first).toBe(true)
    expect(second).toBe(true)
  })

  it('retries apiFetch once after a successful refresh', async () => {
    let welcomeCalls = 0

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'

      if (url === '/auth/refresh' && method === 'POST') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ message: 'Session refreshed' }),
        })
      }

      if (url === '/api/user_welcome') {
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

      return Promise.reject(new Error(`Unexpected fetch: ${url}`))
    })
    globalThis.fetch = fetchMock as typeof fetch

    const result = await apiFetch('/api/user_welcome', { method: 'GET' })

    expect(welcomeCalls).toBe(2)
    expect(result.ok).toBe(true)
    expect(result.data?.message).toBe('Welcome Demo User!')
  })

  it('retries once more when the post-refresh welcome call still returns 401', async () => {
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
        if (welcomeCalls === 2) {
          return Promise.resolve({
            ok: false,
            status: 401,
            json: async () => ({ error: 'Not authenticated' }),
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

    const result = await apiFetch('/api/user_welcome', { method: 'GET' })

    expect(refreshCalls).toBe(1)
    expect(welcomeCalls).toBe(3)
    expect(result.ok).toBe(true)
    expect(result.data?.message).toBe('Welcome Demo User!')
  })
})
