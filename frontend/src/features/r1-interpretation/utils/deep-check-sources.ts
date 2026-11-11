export type SourceKind = 'web' | 'page' | 'reviews' | 'counts' | (string & {})
export type SourceStep = { kind: SourceKind; label: string; text: string }

/** Steps shown before "Show N more". */
export const MAX_VISIBLE_SOURCES = 6

/** A counts step is the rule that decides whether the answer counts, so it always goes last. */
export function orderSources(list: readonly SourceStep[] = []): SourceStep[] {
  return [...list.filter((s) => s.kind !== 'counts'), ...list.filter((s) => s.kind === 'counts')]
}

/** Only the very last step, and only when it is a counts step, takes the outcome tone. */
export function isOutcome(step: SourceStep, index: number, all: readonly SourceStep[]): boolean {
  return step.kind === 'counts' && index === all.length - 1
}
