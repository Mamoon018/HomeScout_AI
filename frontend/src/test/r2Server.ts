import type { Reply } from '@/test/r1Server'

export type R2Call = { method: string; path: string; body: unknown }
type Handler = (call: R2Call) => Reply | Promise<Reply>

const R2 = '/api/amenity-search/runs'
const R1 = '/api/requirement-interpretation/runs'

/**
 * A fake of the R2 run endpoints (and the R1 status read the page makes for the plan) at the
 * network boundary. Paths are reported relative to their own prefix: `POST /`, `GET /<id>`,
 * `POST /<id>/retry`; R1 reads are prefixed `r1 `.
 */
export function mockR2Api(handler: Handler, r1: Handler) {
  const calls: R2Call[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const isR1 = url.startsWith(R1)
    const call: R2Call = {
      method: init?.method ?? 'GET',
      path: (isR1 ? 'r1 ' : '') + (url.replace(isR1 ? R1 : R2, '') || '/'),
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
    }
    calls.push(call)
    const reply = await (isR1 ? r1 : handler)(call)
    if (reply === 'network-error') {
      throw new TypeError('Failed to fetch')
    }
    return new Response(reply.body === undefined ? null : JSON.stringify(reply.body), {
      status: reply.status,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls, fetchMock }
}
