export type AuthUser = {
  user_id: string
  user_name: string | null
}

const AUTH_USER_STORAGE_KEY = 'homescout.auth.user'

/** Persists login identity in localStorage until logout calls clearAuthUser. */
export function saveAuthUser(user: AuthUser): void {
  localStorage.setItem(AUTH_USER_STORAGE_KEY, JSON.stringify(user))
}

/** Returns the stored login identity, or null if missing or invalid. */
export function getAuthUser(): AuthUser | null {
  const raw = localStorage.getItem(AUTH_USER_STORAGE_KEY)
  if (!raw) {
    return null
  }

  try {
    const parsed = JSON.parse(raw) as Partial<AuthUser>
    if (typeof parsed.user_id !== 'string' || !parsed.user_id) {
      return null
    }

    const userName =
      typeof parsed.user_name === 'string' && parsed.user_name.trim()
        ? parsed.user_name
        : null

    return { user_id: parsed.user_id, user_name: userName }
  } catch {
    return null
  }
}

/** Removes stored identity. Call this from logout when that flow exists. */
export function clearAuthUser(): void {
  localStorage.removeItem(AUTH_USER_STORAGE_KEY)
}
