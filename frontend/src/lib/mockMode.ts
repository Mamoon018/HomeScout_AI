/**
 * The mock-mode switch and the guards that run in both modes. Mock mode is on only in a
 * development build with `VITE_USE_MOCK_API=true`; a production build can never turn it on.
 * The mock itself lives in `mocks/` and is never imported from here.
 */
import { clearAuthUser } from '@/features/auth/utils/authUserStore'
import { clearRunId } from '@/features/r1-interpretation/utils/runStorage'
import { clearR2Run } from '@/features/r2-proximity/utils/runStorage'

const MODE_KEY = 'homescout.mode'

/** True only in a dev build whose env sets `VITE_USE_MOCK_API=true`. */
export function isMockMode(): boolean {
  return import.meta.env.DEV === true && import.meta.env.VITE_USE_MOCK_API === 'true'
}

/**
 * Clears this tab's saved runs and user when the mode changed since the last load, so an id
 * from one mode never reaches the other. A missing marker counts as live (the app before mock
 * mode existed). Storage can be blocked: every access is guarded and the page works without it.
 */
export function resetOnModeChange(mockOn: boolean): void {
  const mode = mockOn ? 'mock' : 'live'
  let previous: string | null
  try {
    previous = window.localStorage.getItem(MODE_KEY)
  } catch {
    return
  }
  if ((previous ?? 'live') !== mode) {
    clearRunId()
    clearR2Run()
    try {
      clearAuthUser()
    } catch {
      // Storage blocked: nothing was saved to clear.
    }
  }
  try {
    window.localStorage.setItem(MODE_KEY, mode)
  } catch {
    // Storage blocked or full: the next load simply compares again.
  }
}

/** Live mode only: a mock run id in a request path means state leaked from mock mode. */
export function warnIfMockIdInLive(path: string): void {
  if (!isMockMode() && path.includes('mock_')) {
    console.warn(
      `[mock_state_mixed] ${path} carries a mock run id, but mock mode is off. ` +
        'It probably came from a bookmarked or copied mock URL; start a new run instead.',
    )
  }
}
