import type { LoginApiResponse } from '@/features/auth/api/authApi'

export const LOGIN_USER_MESSAGES = {
  invalidCredentials: 'Invalid email or password',
  connection: 'Unable to connect. Please try again.',
} as const

/** Maps a login API response to a user-facing error message. */
export function getLoginErrorMessage(result: LoginApiResponse): string | null {
  if (result.ok) {
    return null
  }

  if (result.status === 401) {
    return LOGIN_USER_MESSAGES.invalidCredentials
  }

  if (result.status === 429 && result.data?.error) {
    return result.data.error
  }

  if (result.status === 502 || result.aborted || result.networkError) {
    return LOGIN_USER_MESSAGES.connection
  }

  if (result.data?.error) {
    return result.data.error
  }

  return LOGIN_USER_MESSAGES.invalidCredentials
}
