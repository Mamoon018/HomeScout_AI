/**
 * Fixed-size paging used three times on the page: category cards (3 at a time), and the
 * needs inside a card and inside the requirement table (2 at a time). The last page is
 * always full: it slides back rather than showing a lone item.
 */
export type PageWindow = {
  start: number
  end: number
  paged: boolean
  hasPrev: boolean
  hasNext: boolean
  prevStart: number
  nextStart: number
  /** "Needs 1–2 of 4" */
  label: string
  prevLabel: string
  nextLabel: string
}

export function pageWindow(requested: number, total: number, per: number, noun: string, lowerNoun = noun.toLowerCase()): PageWindow {
  const start = Math.max(0, Math.min(requested, total - per))
  const end = Math.min(start + per, total)
  const prevStart = Math.max(0, start - per)
  const nextStart = Math.max(0, Math.min(start + per, total - per))
  return {
    start,
    end,
    paged: total > per,
    hasPrev: start > 0,
    hasNext: start + per < total,
    prevStart,
    nextStart,
    label: `${noun} ${start + 1}–${end} of ${total}`,
    prevLabel: `Show ${lowerNoun} ${prevStart + 1}–${Math.min(prevStart + per, total)}`,
    nextLabel: `Show ${lowerNoun} ${nextStart + 1}–${Math.min(nextStart + per, total)}`,
  }
}
