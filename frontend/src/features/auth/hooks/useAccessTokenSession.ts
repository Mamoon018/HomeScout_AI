import { useEffect, useState } from 'react'
import {
  getAccessTokenSession,
  type AuthApiResponse,
  type CookieReceiveStatus,
} from '@/features/auth/api/authApi'

/** Loads whether the HttpOnly access token cookie is present on this origin. */
export function useAccessTokenSession() {
  const [isLoading, setIsLoading] = useState(true)
  const [result, setResult] = useState<AuthApiResponse<CookieReceiveStatus> | null>(
    null,
  )

  useEffect(() => {
    let cancelled = false

    async function loadSession() {
      const session = await getAccessTokenSession()
      if (!cancelled) {
        setResult(session)
        setIsLoading(false)
      }
    }

    void loadSession()

    return () => {
      cancelled = true
    }
  }, [])

  return {
    isLoading,
    receiveStatus: result?.ok ? result.data : null,
    probeFailed: Boolean(result && !result.ok),
  }
}
