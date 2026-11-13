/**
 * The id of the run on screen, kept for this tab only so a refresh can pick the run up again
 * through the status endpoint. Storage can be blocked or full, so every access is guarded and
 * the page works without it.
 */
const KEY = 'homescout.r1.runId'

export function loadRunId(): string | null {
  try {
    return window.sessionStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function saveRunId(runId: string): void {
  try {
    window.sessionStorage.setItem(KEY, runId)
  } catch {
    /* Not remembered: a refresh starts clean. */
  }
}

export function clearRunId(): void {
  try {
    window.sessionStorage.removeItem(KEY)
  } catch {
    /* Nothing to clear. */
  }
}
