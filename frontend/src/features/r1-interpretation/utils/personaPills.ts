/** Deep accents a fact pill can take: amber, blue, rose, orange, green. */
const PILL_ACCENTS = [
  'var(--color-Step-1)',
  'var(--color-Step-4)',
  'var(--color-Step-2)',
  'var(--color-Step-3)',
  'var(--fs-done)',
] as const

const MAX_PILLS = 3

/** Small seeded generator, so the same facts always pick the same pills. */
function seededRandom(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/**
 * Which facts get a coloured pill, and which accent each takes. Seeded from the facts
 * themselves: stable between renders, different for different briefs.
 */
export function pickPills(facts: string[]): Map<number, string> {
  const seed = [...facts.join('|')].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 7)
  const random = seededRandom(seed)
  const indices = facts.map((_, i) => i)
  const accents = [...PILL_ACCENTS]
  const picked = new Map<number, string>()
  for (let n = 0; n < Math.min(MAX_PILLS, facts.length); n += 1) {
    const at = Math.floor(random() * indices.length)
    const [index] = indices.splice(at, 1)
    const [accent] = accents.splice(Math.floor(random() * accents.length), 1)
    picked.set(index, accent)
  }
  return picked
}

