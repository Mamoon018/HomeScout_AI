/** Shared same-origin fetch with reactive refresh-and-retry on token expiry. */

export type ApiErrorBody = {
  error?: string
  code?: string
}

export type ApiResponse<T> = {
  ok: boolean
  status: number
  data: T | null
  aborted?: boolean
  networkError?: boolean
}

export type ApiFetchOptions = {
  skipRefresh?: boolean
  _retried?: boolean
  _staleCookieRetry?: boolean
}

const API_TIMEOUT_MS = 15000

let refreshInFlight: Promise<boolean> | null = null

/** Returns true when a 401 body signals an expired access token worth refreshing. */
function isTokenExpired401(data: ApiErrorBody | null, status: number): boolean {
  return status === 401 && data?.code === 'token_expired'
}

/** Performs a timed same-origin JSON request with credentials included. */
export async function fetchJson<T>(
  path: string,
  init: RequestInit,
): Promise<ApiResponse<T>> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), API_TIMEOUT_MS)

  try {
    const response = await fetch(path, {
      ...init,
      credentials: 'include',
      signal: controller.signal,
    })

    let data: T | null = null
    try {
      data = (await response.json()) as T
    } catch {
      data = null
    }

    return {
      ok: response.ok,
      status: response.status,
      data,
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return {
        ok: false,
        status: 0,
        data: null,
        aborted: true,
      }
    }

    if (error instanceof TypeError) {
      return {
        ok: false,
        status: 0,
        data: null,
        networkError: true,
      }
    }

    throw error
  } finally {
    clearTimeout(timeout)
  }
}

async function doRefresh(): Promise<boolean> {
  const { refreshSession } = await import('@/features/auth/api/authApi')
  const result = await refreshSession()
  return result.ok
}

/** Deduplicates concurrent refresh calls across expired API requests in this tab. */
export async function ensureRefreshed(): Promise<boolean> {
  if (refreshInFlight) {
    return refreshInFlight
  }

  refreshInFlight = doRefresh().finally(() => {
    refreshInFlight = null
  })

  return refreshInFlight
}

/** Resets refresh dedup state — for tests only. */
export function resetRefreshStateForTests(): void {
  refreshInFlight = null
}

/** Yields so the browser can commit Set-Cookie from the refresh response. */
async function commitSessionCookies(): Promise<void> {
  await new Promise<void>((resolve) => {
    setTimeout(resolve, 0)
  })
}

/** Fetches JSON and transparently refreshes once when the access token expired. */
export async function apiFetch<T>(
  path: string,
  init: RequestInit,
  options: ApiFetchOptions = {},
): Promise<ApiResponse<T>> {
  if (refreshInFlight && !options.skipRefresh) {
    await refreshInFlight
    await commitSessionCookies()
  }

  const result = await fetchJson<T & ApiErrorBody>(path, init)

  if (
    !options.skipRefresh &&
    !options._retried &&
    isTokenExpired401(result.data, result.status)
  ) {
    const refreshed = await ensureRefreshed()
    if (refreshed) {
      await commitSessionCookies()
      return apiFetch<T>(path, init, { ...options, _retried: true })
    }
  }

  if (
    !options.skipRefresh &&
    options._retried &&
    !options._staleCookieRetry &&
    result.status === 401
  ) {
    await commitSessionCookies()
    return apiFetch<T>(path, init, { ...options, _staleCookieRetry: true })
  }

  return result
}
