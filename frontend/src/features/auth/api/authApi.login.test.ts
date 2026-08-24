import { login } from '@/features/auth/api/authApi'

describe('authApi.login', () => {
  const originalFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.useRealTimers()
  })

  it('posts to the same-origin login path and parses success response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        message: 'Login successful',
        cookie: {
          sent: true,
          name: 'access_token',
          http_only: true,
          secure: true,
          same_site: 'Strict',
          path: '/',
        },
      }),
    })
    globalThis.fetch = fetchMock

    const result = await login({
      email: 'demo@homescout.ai',
      password: 'password123',
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/login',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: 'demo@homescout.ai',
          password: 'password123',
        }),
      }),
    )
    expect(result.ok).toBe(true)
    expect(result.status).toBe(200)
    expect(result.data?.cookie?.same_site).toBe('Strict')
  })

  it('returns aborted response when fetch times out at 15s', async () => {
    vi.useFakeTimers()

    const fetchMock = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'))
          })
        }),
    )
    globalThis.fetch = fetchMock as typeof fetch

    const loginPromise = login({
      email: 'demo@homescout.ai',
      password: 'password123',
    })

    await vi.advanceTimersByTimeAsync(15000)

    const result = await loginPromise
    expect(result).toEqual({
      ok: false,
      status: 0,
      data: null,
      aborted: true,
    })
  })
})
