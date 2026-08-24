import { useLocation, useNavigate } from 'react-router-dom'
import { AuthCookieStatus } from '@/components/auth-cookie-status'
import { Button } from '@/components/ui/button'
import type { CookieSendStatus } from '@/features/auth/api/authApi'
import { useAccessTokenSession } from '@/features/auth/hooks/useAccessTokenSession'

type CallbackLocationState = {
  cookie?: CookieSendStatus | null
}

/** Confirms the HttpOnly cookie landed before continuing to the homepage. */
export function AuthCallbackPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const sendStatus = (location.state as CallbackLocationState | null)?.cookie ?? null
  const { isLoading, receiveStatus, probeFailed } = useAccessTokenSession()
  const cookieLanded = Boolean(
    receiveStatus?.present && receiveStatus.matches_expected,
  )

  return (
    <main className="flex min-h-svh items-center justify-center bg-background px-6 text-foreground">
      <div className="w-full max-w-md text-center">
        <h1 className="text-2xl font-medium tracking-tight">Checking session cookie</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {cookieLanded
            ? 'Cookie verified on this origin. You can continue to home.'
            : 'A 200 login response is not enough — the cookie must persist on this origin.'}
        </p>
        <AuthCookieStatus
          sendStatus={sendStatus}
          receiveStatus={receiveStatus}
          isLoading={isLoading}
          probeFailed={probeFailed}
        />
        <Button
          className="mt-4"
          disabled={!cookieLanded}
          onClick={() => navigate('/home', { replace: true })}
        >
          Continue
        </Button>
      </div>
    </main>
  )
}
