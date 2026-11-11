/** One clarification question, exactly as R1 returns it while the run is `needs_answers`. */
export type ClarificationQuestion = {
  category_id: number
  /** The renter's own phrase that R1 could not map to a known amenity type. */
  category: string
  question: string
  /** Exactly five; the last one is always the literal "other". */
  options: string[]
}

/** One answer, as the answers endpoint expects it. `option` is 1-based ("other" is always last). */
export type ClarificationAnswer = {
  category_id: number
  option: number
  /** The chosen option's text, or what the renter typed when they chose "other". */
  description: string
}

/** none = nothing to ask · asking = waiting for the renter · answered = summary shown. */
export type ClarificationPhase = 'none' | 'asking' | 'answered'

/** Longest "other" description we accept. Placeholder until the backend states a limit. */
export const OTHER_MAX_LENGTH = 200
