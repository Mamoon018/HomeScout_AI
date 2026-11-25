/**
 * The dev mock's one entry point. `main.tsx` loads it with a DEV-only dynamic import when mock
 * mode is on; nothing else imports `mocks/` (react_code_rules, rule 17).
 */
import { installMockFetch } from '@/mocks/mockFetch'
import { readScenario, type Scenario } from '@/mocks/mockScenario'

/** Picks the scenario from the page's query string and starts answering backend calls. */
export function startMockMode(search: string): Scenario {
  const scenario = readScenario(search)
  installMockFetch({ scenario })
  return scenario
}
