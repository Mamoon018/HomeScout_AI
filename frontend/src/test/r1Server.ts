/** A fake of the four run endpoints at the network boundary: `fetch`. */
export type Reply = { status: number; body?: unknown } | 'network-error'
export type Call = { method: string; path: string; body: unknown }
type Handler = (call: Call) => Reply | Promise<Reply>

export function mockRunApi(handler: Handler) {
  const calls: Call[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const call: Call = {
      method: init?.method ?? 'GET',
      path: url.replace('/api/requirement-interpretation/runs', '') || '/',
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
    }
    calls.push(call)
    const reply = await handler(call)
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

/** A brief long enough for the composer to accept (the backend wants 100 words). */
export const LONG_BRIEF = Array.from({ length: 120 }, (_, i) => `word${i}`).join(' ')
