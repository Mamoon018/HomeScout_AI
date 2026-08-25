import { getAuthUser } from '@/features/auth/utils/authUserStore'

/** Authenticated homepage showing the stored user name from login. */
export function HomePage() {
  const userName = getAuthUser()?.user_name

  return (
    <main className="flex min-h-svh items-center justify-center bg-background px-6 text-foreground">
      <div className="w-full max-w-md text-center">
        {userName ? (
          <h1 className="text-3xl font-medium tracking-tight">
            Welcome {userName}!
          </h1>
        ) : null}
        <p className="mt-2 text-sm text-muted-foreground">You are signed in.</p>
      </div>
    </main>
  )
}
