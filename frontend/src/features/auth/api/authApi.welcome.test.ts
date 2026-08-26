import { getUserWelcome } from '@/features/auth/api/authApi'

describe('authApi.getUserWelcome', () => {
  const originalFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = originalFetch
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
})
