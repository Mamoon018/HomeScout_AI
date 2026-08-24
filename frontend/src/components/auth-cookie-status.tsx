import type { CookieReceiveStatus, CookieSendStatus } from '@/features/auth/api/authApi'

type AuthCookieStatusProps = {
  sendStatus?: CookieSendStatus | null
  receiveStatus?: CookieReceiveStatus | null
  isLoading?: boolean
  probeFailed?: boolean
}

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}

function formatBoolean(value: boolean | undefined): string {
  if (value === undefined) {
    return 'unknown'
  }
  return value ? 'yes' : 'no'
}

/** Shows cookie send vs receive status because HttpOnly cookies are invisible to JS. */
export function AuthCookieStatus({
  sendStatus,
  receiveStatus,
  isLoading = false,
  probeFailed = false,
}: AuthCookieStatusProps) {
  return (
    <section className="mx-auto mt-6 w-full max-w-md rounded-xl border border-border bg-card px-4 py-4 text-left">
      <h2 className="text-sm font-medium">Cookie probe</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        HttpOnly cookies never appear in document.cookie. Use this probe and DevTools
        Application → Cookies for https://localhost:5173.
      </p>

      <div className="mt-4 space-y-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Backend send
        </p>
        <StatusRow label="Set-Cookie attached" value={formatBoolean(sendStatus?.sent)} />
        <StatusRow label="Name" value={sendStatus?.name ?? 'unknown'} />
        <StatusRow label="HttpOnly" value={formatBoolean(sendStatus?.http_only)} />
        <StatusRow label="Secure" value={formatBoolean(sendStatus?.secure)} />
        <StatusRow
          label="SameSite"
          value={sendStatus?.same_site ?? 'unknown'}
        />
      </div>

      <div className="mt-4 space-y-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Browser receive
        </p>
        {isLoading ? (
          <p className="text-sm">Checking whether the cookie was sent back…</p>
        ) : probeFailed ? (
          <p className="text-sm text-destructive">
            Session probe failed. Confirm the Vite proxy and backend are running.
          </p>
        ) : (
          <>
            <StatusRow
              label="Cookie present on request"
              value={formatBoolean(receiveStatus?.present)}
            />
            <StatusRow
              label="Matches server token"
              value={formatBoolean(receiveStatus?.matches_expected)}
            />
          </>
        )}
      </div>
    </section>
  )
}
