/** Dummy run timing (ms). Replace with real progress events once the backend reports them. */
export const R1_TIMING = {
  headingFade: 200,
  composerMove: 400,
  /** Extraction streams in; the run then asks questions or moves on to planning. */
  extract: 2800,
  /** Deciding what to look for, after the last answer. */
  plan: 2400,
  /** Result and breakdown fade out before a re-run. */
  resetFade: 200,
  resetSettle: 300,
  /** Gap between two streamed rows. */
  rowStagger: 90,
} as const
