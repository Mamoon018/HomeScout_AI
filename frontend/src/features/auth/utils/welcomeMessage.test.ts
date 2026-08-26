import { welcomeMessageFromResponse } from '@/features/auth/utils/welcomeMessage'

describe('welcomeMessageFromResponse', () => {
  it('returns the API message on success', () => {
    const onUnauthenticated = vi.fn()
    expect(
      welcomeMessageFromResponse(
        { ok: true, status: 200, data: { message: 'Welcome Demo User!' } },
        onUnauthenticated,
      ),
    ).toBe('Welcome Demo User!')
    expect(onUnauthenticated).not.toHaveBeenCalled()
  })

  it('calls onUnauthenticated and returns null on 401', () => {
    const onUnauthenticated = vi.fn()
    expect(
      welcomeMessageFromResponse(
        { ok: false, status: 401, data: { error: 'Not authenticated' } },
        onUnauthenticated,
      ),
    ).toBeNull()
    expect(onUnauthenticated).toHaveBeenCalledTimes(1)
  })

  it('returns null when the API has no message', () => {
    const onUnauthenticated = vi.fn()
    expect(
      welcomeMessageFromResponse(
        { ok: true, status: 200, data: {} },
        onUnauthenticated,
      ),
    ).toBeNull()
    expect(onUnauthenticated).not.toHaveBeenCalled()
  })
})
