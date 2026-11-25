/**
 * Fixed, pre-built run ids: one per scenario and stage (`mock_error_r2`). The id carries its
 * scenario, so the mock can answer any call for it after a reload or after the app rewrote the
 * URL, and the R3 → R2 → R1 chain always resolves.
 */
import { isScenario, type Scenario } from '@/mocks/mockScenario'

export type Stage = 'r1' | 'r2' | 'r3'

export const MOCK_ID_PREFIX = 'mock_'

export function idsFor(scenario: Scenario): Record<Stage, string> {
  return {
    r1: `${MOCK_ID_PREFIX}${scenario}_r1`,
    r2: `${MOCK_ID_PREFIX}${scenario}_r2`,
    r3: `${MOCK_ID_PREFIX}${scenario}_r3`,
  }
}

/** The scenario and stage a fixed id stands for, or null when it is not one of the table's ids. */
export function parseMockId(id: string): { scenario: Scenario; stage: Stage } | null {
  const match = /^mock_(.+)_(r[123])$/.exec(id)
  if (!match || !isScenario(match[1])) return null
  return { scenario: match[1], stage: match[2] as Stage }
}
