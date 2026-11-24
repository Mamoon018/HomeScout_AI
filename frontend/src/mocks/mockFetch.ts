/**
 * Wraps `window.fetch` so backend calls (`/api/*`, `/auth/refresh`) are answered in the browser,
 * in the backend's own shapes. Everything else (Supabase, Turnstile, assets) goes to the real
 * fetch untouched. An `/api` path the table does not know gets a loud 501, never the real backend.
 */
import { createRoutes } from '@/mocks/mockRoutes'
import { createRunStore, type Reply, type RunStore } from '@/mocks/mockRunStore'
import type { Scenario } from '@/mocks/mockScenario'

/** Unique to the mock code: the production build fails if it appears in `dist/`. */
export const MOCK_MARKER = 'HOMESCOUT_DEV_MOCK_BACKEND'

export const DEFAULT_DELAY_MS = 300

type Options = { scenario: Scenario; delayMs?: number; store?: RunStore; banner?: boolean }

function isBackendPath(url: URL): boolean {
  return url.origin === window.location.origin && (url.pathname.startsWith('/api/') || url.pathname === '/auth/refresh')
}

/** Waits like a network reply would, and stops at once if the caller aborts. */
function wait(ms: number, signal: AbortSignal | null | undefined): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException('The operation was aborted.', 'AbortError'))
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(new DOMException('The operation was aborted.', 'AbortError'))
    })
  })
}

/** Installs the interceptor and returns a function that restores the real fetch. */
export function installMockFetch({ scenario, delayMs = DEFAULT_DELAY_MS, store = createRunStore(), banner = true }: Options) {
  const realFetch = window.fetch.bind(window)
  const route = createRoutes(scenario, store)

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const url = new URL(raw, window.location.origin)
    if (!isBackendPath(url)) return realFetch(input, init)

    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase()
    let reply: Reply | null = route(method, url.pathname)
    if (!reply) {
      console.error(`[mock_unhandled_route] ${method} ${url.pathname} has no mock route.`)
      reply = { status: 501, body: { error: 'No mock route', code: 'mock_unhandled_route' } }
    }

    await wait(reply.delayMs ?? delayMs, init?.signal)
    return new Response(JSON.stringify(reply.body), {
      status: reply.status,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  if (banner) {
    console.info(`[${MOCK_MARKER}] Mock mode is on, scenario "${scenario}". Backend calls are answered in the browser.`)
  }
  return () => {
    window.fetch = realFetch
  }
}
