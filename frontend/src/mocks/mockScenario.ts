/** The UI states the dev mock can play, picked with `?mock=<name>` when the page loads. */
export const SCENARIOS = [
  'happy',
  'running',
  'paused',
  'error',
  'not-found',
  'empty',
  'slow',
  'unauthenticated',
] as const

export type Scenario = (typeof SCENARIOS)[number]

export const DEFAULT_SCENARIO: Scenario = 'happy'

export function isScenario(value: string): value is Scenario {
  return (SCENARIOS as readonly string[]).includes(value)
}

/** Reads `?mock=` from a query string; an unknown name falls back to `happy` with a warning. */
export function readScenario(search: string): Scenario {
  const name = new URLSearchParams(search).get('mock')
  if (name === null || name === '') return DEFAULT_SCENARIO
  if (isScenario(name)) return name
  console.warn(
    `[mock_unknown_scenario] "?mock=${name}" is not a scenario; using "${DEFAULT_SCENARIO}". ` +
      `Known: ${SCENARIOS.join(', ')}.`,
  )
  return DEFAULT_SCENARIO
}
