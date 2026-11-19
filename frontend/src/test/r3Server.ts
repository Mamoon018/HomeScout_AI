import type { Reply } from '@/test/r1Server'

export type R3Call = { method: string; path: string; body: unknown }
type Handler = (call: R3Call) => Reply | Promise<Reply>

const PREFIXES: [string, string][] = [
  ['/api/specific-metric-resolution/runs', 'r3'],
  ['/api/amenity-search/runs', 'r2'],
  ['/api/requirement-interpretation/runs', 'r1'],
]

/**
 * A fake of the R3 run endpoints and the R1/R2 status reads the page makes, at the network
 * boundary (`fetch`). Each call is reported as `<r1|r2|r3> <METHOD> <path after the prefix>`,
 * e.g. `r3 POST /` or `r2 GET /<id>`; an unexpected call fails the test.
 */
export function mockR3Api(routes: Record<string, Handler>) {
  const calls: string[] = []
  const bodies: unknown[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const [prefix, tag] = PREFIXES.find(([p]) => url.startsWith(p)) ?? ['', '?']
    const key = `${tag} ${init?.method ?? 'GET'} ${url.replace(prefix, '') || '/'}`
    calls.push(key)
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
    bodies.push(body)
    const route = routes[key]
    if (!route) throw new Error(`Unexpected call: ${key}`)
    const reply = await route({ method: init?.method ?? 'GET', path: key, body })
    if (reply === 'network-error') throw new TypeError('Failed to fetch')
    return new Response(reply.body === undefined ? null : JSON.stringify(reply.body), {
      status: reply.status,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls, bodies, fetchMock }
}
