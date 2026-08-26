import type { WelcomeApiResponse } from '@/features/auth/api/authApi'

/** Maps the welcome API result to displayed copy, or signals an unbound session. */
export function welcomeMessageFromResponse(
  result: WelcomeApiResponse,
  onUnauthenticated: () => void,
): string | null {
  if (result.status === 401) {
    onUnauthenticated()
    return null
  }

  if (result.ok && result.data?.message) {
    return result.data.message
  }

  return null
}
