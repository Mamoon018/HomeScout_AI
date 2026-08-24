import { AuthCookieStatus } from '@/components/auth-cookie-status'
import { useAccessTokenSession } from '@/features/auth/hooks/useAccessTokenSession'

/** Dummy authenticated homepage with a live cookie presence probe. */
export function HomePage() {
  const { isLoading, receiveStatus, probeFailed } = useAccessTokenSession()

  return (
    <main className="flex min-h-svh items-center justify-center bg-background px-6 text-foreground">
      <div className="w-full max-w-md text-center">
        <h1 className="text-3xl font-medium tracking-tight">Welcome to HomeScout</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          You are signed in.
        </p>
        <AuthCookieStatus
          receiveStatus={receiveStatus}
          isLoading={isLoading}
          probeFailed={probeFailed}
        />
      </div>
    </main>
  )
}
