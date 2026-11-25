/**
 * The R3 run on screen, kept for this tab beside the R2 run it started from, so coming back to
 * R3 for the same amenity search reopens it instead of starting again. Storage can be blocked
 * or full: every access is guarded and the page works without it.
 */
const KEY = 'homescout.r3.run'

export type SavedR3Run = {
  runId: string
  r2RunId: string
}

export function loadR3Run(): SavedR3Run | null {
  try {
    const raw = window.sessionStorage.getItem(KEY)
    if (!raw) {
      return null
    }
    const v = JSON.parse(raw) as Partial<SavedR3Run>
    return typeof v.runId === 'string' && typeof v.r2RunId === 'string' ? (v as SavedR3Run) : null
  } catch {
    return null
  }
}

export function saveR3Run(run: SavedR3Run): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(run))
  } catch {
    /* Not remembered: coming back starts from the start screen. */
  }
}

export function clearR3Run(): void {
  try {
    window.sessionStorage.removeItem(KEY)
  } catch {
    /* Nothing to clear. */
  }
}
