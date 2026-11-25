import type { R2RunView } from '@/features/r2-proximity/types/r2'
import type { SavedR2Run } from '@/features/r2-proximity/utils/runStorage'

/**
 * Fills the parts of a saved R2 run this tab does not know (its R1 run, origin, radius) from a
 * run response, which carries them on every status. A run opened from a link in another tab
 * starts with none of them; after its first response it has all three, so the page can load the
 * R1 plan and show the search area. Values the tab already has are never overwritten.
 *
 * Data path: GET /runs/<id> → normalizeR2Run → useR2Run.apply → completeSavedRun → saveR2Run →
 * the R1 plan effect in useR2Run → ProximityPage.
 *
 * Returns the same object when nothing was missing or the response could not fill it.
 */
export function completeSavedRun(saved: SavedR2Run, view: R2RunView): SavedR2Run {
  const r1RunId = saved.r1RunId || view.r1RunId || ''
  const hasOrigin = Number.isFinite(saved.latitude) && Number.isFinite(saved.longitude)
  const latitude = hasOrigin ? saved.latitude : (view.origin?.latitude ?? saved.latitude)
  const longitude = hasOrigin ? saved.longitude : (view.origin?.longitude ?? saved.longitude)
  const radiusKm = Number.isFinite(saved.radiusKm) ? saved.radiusKm : (view.radiusKm ?? saved.radiusKm)

  if (
    r1RunId === saved.r1RunId &&
    Object.is(latitude, saved.latitude) &&
    Object.is(longitude, saved.longitude) &&
    Object.is(radiusKm, saved.radiusKm)
  ) {
    return saved
  }
  return { ...saved, r1RunId, latitude, longitude, radiusKm }
}
