import { getAccessTokenSession } from '@/features/auth/api/authApi'

describe('authApi.getAccessTokenSession', () => {
  const originalFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('probes the same-origin session path with credentials', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        present: true,
        matches_expected: true,
        name: 'access_token',
      }),
    })
    globalThis.fetch = fetchMock

    const result = await getAccessTokenSession()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/session',
      expect.objectContaining({
        method: 'GET',
        credentials: 'include',
      }),
    )
    expect(result).toEqual({
      ok: true,
      status: 200,
      data: {
        present: true,
        matches_expected: true,
        name: 'access_token',
      },
    })
  })
})
