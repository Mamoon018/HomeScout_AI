/**
 * The mock's route table: method + path → reply, for every backend endpoint the app calls
 * (`features/auth/api/authApi`, `r1Api`, `r2Api`, `r3Api`). Null means the path is not mocked.
 */
import type { Reply, RunStore } from '@/mocks/mockRunStore'
import type { Scenario } from '@/mocks/mockScenario'
import type { Stage } from '@/mocks/mockRunIds'

const RUN_PREFIXES: [string, Stage][] = [
  ['/api/requirement-interpretation/runs', 'r1'],
  ['/api/amenity-search/runs', 'r2'],
  ['/api/specific-metric-resolution/runs', 'r3'],
]

const MOCK_USER = { user_id: 'mock_user', user_name: 'Mock Renter' }

export function createRoutes(scenario: Scenario, store: RunStore) {
  const signedOut = scenario === 'unauthenticated'

  return function route(method: string, path: string): Reply | null {
    if (method === 'POST' && path === '/api/auth/login') {
      return { status: 200, body: { message: 'Login successful', ...MOCK_USER } }
    }
    if (method === 'POST' && path === '/auth/refresh') {
      return signedOut
        ? { status: 401, body: { error: 'Not signed in' } }
        : { status: 200, body: { message: 'Session refreshed' } }
    }
    if (method === 'GET' && path === '/api/user_welcome') {
      return signedOut
        ? { status: 401, body: { error: 'Not signed in', code: 'token_expired' } }
        : { status: 200, body: { message: `Welcome back, ${MOCK_USER.user_name}` } }
    }

    for (const [prefix, stage] of RUN_PREFIXES) {
      if (path !== prefix && !path.startsWith(`${prefix}/`)) continue
      const rest = path.slice(prefix.length).split('/').filter(Boolean).map(decodeURIComponent)

      if (rest.length === 0 && method === 'POST') return store.start(scenario, stage)
      if (rest.length === 1 && method === 'GET') return store.read(rest[0], stage)
      if (rest.length === 2 && method === 'POST' && rest[1] === 'retry') return store.retry(rest[0], stage)
      if (rest.length === 2 && method === 'POST' && rest[1] === 'clarification-answers' && stage === 'r1') {
        return store.answer(rest[0])
      }
      return null
    }
    return null
  }
}
