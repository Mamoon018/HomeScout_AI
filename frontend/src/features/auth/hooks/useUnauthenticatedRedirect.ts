import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { clearAuthUser } from '@/features/auth/utils/authUserStore'

/**
 * The one place that handles a lost session: clears the stored user and sends the renter to
 * sign in. Pages pass the returned callback to their run hooks as `onUnauthenticated`.
 */
export function useUnauthenticatedRedirect(): () => void {
  const navigate = useNavigate()

  return useCallback(() => {
    clearAuthUser()
    navigate('/auth/login', { replace: true })
  }, [navigate])
}
