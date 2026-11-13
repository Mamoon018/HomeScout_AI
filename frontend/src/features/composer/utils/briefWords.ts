/**
 * The fewest words the backend accepts in a brief (`MIN_INPUT_WORD_COUNT`). Shorter ones get a
 * 422 before any run exists, so the composer holds the send button back instead.
 */
export const MIN_BRIEF_WORDS = 100

/** Words the way the backend counts them: runs of non-space characters. */
export function countWords(text: string): number {
  const trimmed = text.trim()
  return trimmed === '' ? 0 : trimmed.split(/\s+/).length
}
