/**
 * The R2 run on screen, kept for this tab so a refresh can pick it up through the status
 * endpoint. The R1 run, origin and radius are kept beside the id so the page can show them
 * before the first response; a tab without them takes them from that response
 * (completeSavedRun). Storage can be blocked or full: every access is guarded.
 */
const KEY = 'homescout.r2.run'

export type SavedR2Run = {
  runId: string
  r1RunId: string
  latitude: number
  longitude: number
  radiusKm: number
}

export function loadR2Run(): SavedR2Run | null {
  try {
    const raw = window.sessionStorage.getItem(KEY)
    if (!raw) {
      return null
    }
    const v = JSON.parse(raw) as Partial<SavedR2Run>
    if (
      typeof v.runId === 'string' &&
      typeof v.r1RunId === 'string' &&
      typeof v.latitude === 'number' &&
      typeof v.longitude === 'number' &&
      typeof v.radiusKm === 'number'
    ) {
      return v as SavedR2Run
    }
    return null
  } catch {
    return null
  }
}

export function saveR2Run(run: SavedR2Run): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(run))
  } catch {
    /* Not remembered: a refresh starts clean. */
  }
}

export function clearR2Run(): void {
  try {
    window.sessionStorage.removeItem(KEY)
  } catch {
    /* Nothing to clear. */
  }
}
