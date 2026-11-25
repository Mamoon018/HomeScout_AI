import type { R2RunView } from '@/features/r2-proximity/types/r2'
import { completeSavedRun } from '@/features/r2-proximity/utils/completeSavedRun'
import type { SavedR2Run } from '@/features/r2-proximity/utils/runStorage'

const view = (over: Partial<R2RunView> = {}): R2RunView => ({
  runId: 'r2',
  status: 'running',
  completedStep: null,
  result: null,
  retryable: null,
  r1RunId: 'r1-from-response',
  origin: { latitude: 48.1374, longitude: 11.5755 },
  radiusKm: 3,
  ...over,
})

/** What the page knows about a run opened from a link: nothing but its id. */
const unknown: SavedR2Run = { runId: 'r2', r1RunId: '', latitude: NaN, longitude: NaN, radiusKm: NaN }

describe('completeSavedRun', () => {
  it('fills the R1 run, origin and radius a link-opened run is missing', () => {
    expect(completeSavedRun(unknown, view())).toEqual({
      runId: 'r2',
      r1RunId: 'r1-from-response',
      latitude: 48.1374,
      longitude: 11.5755,
      radiusKm: 3,
    })
  })

  it('never overwrites what the tab already has', () => {
    const known: SavedR2Run = { runId: 'r2', r1RunId: 'r1-saved', latitude: 50.1, longitude: 8.6, radiusKm: 2 }
    expect(completeSavedRun(known, view())).toBe(known)
  })

  it('fills each field on its own', () => {
    const partial: SavedR2Run = { runId: 'r2', r1RunId: 'r1-saved', latitude: NaN, longitude: NaN, radiusKm: 2 }
    expect(completeSavedRun(partial, view())).toEqual({ ...partial, latitude: 48.1374, longitude: 11.5755 })
  })

  it('leaves a field missing when the response lacks it too, returning the same object', () => {
    const empty = view({ r1RunId: null, origin: null, radiusKm: null })
    expect(completeSavedRun(unknown, empty)).toBe(unknown)
  })
})
