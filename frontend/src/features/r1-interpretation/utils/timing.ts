/** Intro and re-run timing (ms). The run's own phases follow the server, not a clock. */
export const R1_TIMING = {
  headingFade: 200,
  composerMove: 400,
  /** Result and breakdown fade out before a re-run. */
  resetFade: 200,
  resetSettle: 300,
  /** Gap between two streamed rows. */
  rowStagger: 90,
} as const
