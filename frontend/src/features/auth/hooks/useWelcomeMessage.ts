import { useEffect, useState } from 'react'
import { getUserWelcome } from '@/features/auth/api/authApi'
import { welcomeMessageFromResponse } from '@/features/auth/utils/welcomeMessage'

/**
 * Asks the welcome API whether the session is bound and returns its message (null until it
 * answers, or if it has none). A 401 calls `onUnauthenticated`.
 *
 * Data path: useWelcomeMessage → authApi.getUserWelcome → Backend → welcomeMessageFromResponse → HomePage
 */
export function useWelcomeMessage(onUnauthenticated: () => void): string | null {
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    getUserWelcome()
      .then((result) => {
        if (cancelled) {
          return
        }
        const nextMessage = welcomeMessageFromResponse(result, onUnauthenticated)
        if (nextMessage) {
          setMessage(nextMessage)
        }
      })
      .catch(() => {
        /* Leave the homepage empty; 401 already redirects via onUnauthenticated. */
      })

    return () => {
      cancelled = true
    }
  }, [onUnauthenticated])

  return message
}
