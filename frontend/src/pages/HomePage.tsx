type HomePageProps = {
  message: string | null
}

/** Authenticated homepage. Greeting comes from the identity-scoped welcome API. */
export function HomePage({ message }: HomePageProps) {
  return (
    <main className="flex min-h-svh items-center justify-center bg-background px-6 text-foreground">
      <div className="w-full max-w-md text-center">
        {message ? (
          <>
            <h1 className="text-3xl font-medium tracking-tight">{message}</h1>
            <p className="mt-2 text-sm text-muted-foreground">You are signed in.</p>
          </>
        ) : null}
      </div>
    </main>
  )
}
