import {
  getRun,
  retryRun,
  startRun,
  submitAnswers,
  toWireAnswers,
} from '@/features/r1-interpretation/api/r1Api'
import { BODY, RUN_FAILED_BODY, RUN_ID } from '@/test/fixtures/r1Bodies'
import { QUESTIONS } from '@/test/fixtures/r1Questions'
import { mockRunApi, type Reply } from '@/test/r1Server'

afterEach(() => {
  vi.unstubAllGlobals()
})

async function resultOf(reply: Reply) {
  mockRunApi(() => reply)
  return startRun('a brief')
}

describe('toWireAnswers', () => {
  it('sends the description only when the renter chose "other"', () => {
    const [question] = QUESTIONS
    const other = question.options.length
    expect(
      toWireAnswers(
        [{ category_id: question.category_id, option: 1, description: question.options[0] }],
        QUESTIONS,
      ),
    ).toEqual([{ category_id: question.category_id, option: 1 }])
    expect(
      toWireAnswers(
        [{ category_id: question.category_id, option: other, description: 'a sunny roof' }],
        QUESTIONS,
      ),
    ).toEqual([{ category_id: question.category_id, option: other, description: 'a sunny roof' }])
  })
})

describe('run endpoints', () => {
  it("call each endpoint with the contract's method, path and body", async () => {
    const { calls } = mockRunApi(() => ({ status: 200, body: BODY.paused }))
    await startRun('my brief')
    await submitAnswers(RUN_ID, [{ category_id: 7, option: 1 }])
    await retryRun(RUN_ID)
    await getRun(RUN_ID)
    expect(calls).toEqual([
      { method: 'POST', path: '/', body: { requirements: 'my brief' } },
      {
        method: 'POST',
        path: `/${RUN_ID}/clarification-answers`,
        body: { answers: [{ category_id: 7, option: 1 }] },
      },
      { method: 'POST', path: `/${RUN_ID}/retry`, body: undefined },
      { method: 'GET', path: `/${RUN_ID}`, body: undefined },
    ])
  })

  it('return the normalized run on success', async () => {
    const result = await resultOf({ status: 201, body: BODY.paused })
    expect(result.ok && result.view.status).toBe('needs_answers')
  })

  it.each<[string, Reply, object]>([
    [
      '422 with a reason',
      { status: 422, body: { error: 'Instructions must be written in English' } },
      { kind: 'rejected', message: 'Instructions must be written in English' },
    ],
    [
      '422 from schema validation',
      { status: 422, body: { detail: [{ msg: 'x' }] } },
      { kind: 'rejected', message: '' },
    ],
    ['404', { status: 404, body: { error: 'Run not found' } }, { kind: 'not_found' }],
    [
      '409',
      { status: 409, body: { error: 'x', run_id: RUN_ID, status: 'finished' } },
      { kind: 'conflict', runId: RUN_ID },
    ],
    ['401', { status: 401, body: { error: 'Not authenticated' } }, { kind: 'unauthenticated' }],
    [
      '503 about a run',
      { status: 503, body: RUN_FAILED_BODY(true) },
      { kind: 'run_failed', runId: RUN_ID, retryable: true },
    ],
    [
      '502 about a run, no retry left',
      { status: 502, body: RUN_FAILED_BODY(false) },
      { kind: 'run_failed', runId: RUN_ID, retryable: false },
    ],
    [
      '503 with no run (storage down)',
      { status: 503, body: { error: 'Run storage is unavailable' } },
      { kind: 'unavailable' },
    ],
    ['500 with no body', { status: 500 }, { kind: 'unavailable' }],
    ['network failure', 'network-error', { kind: 'network' }],
  ])('classify %s', async (_name, reply, error) => {
    expect(await resultOf(reply)).toEqual({ ok: false, error })
  })

  it('treat a 2xx body the page cannot read as unavailable', async () => {
    expect(await resultOf({ status: 200, body: { run_id: RUN_ID, status: 'paused' } })).toEqual({
      ok: false,
      error: { kind: 'unavailable' },
    })
  })

  it('give start 45 seconds and reading a run the 15 second default', async () => {
    vi.useFakeTimers()
    try {
      const aborted: string[] = []
      vi.stubGlobal(
        'fetch',
        vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
          const path = String(input)
          return new Promise((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () => {
              aborted.push(path)
              reject(new DOMException('aborted', 'AbortError'))
            })
          })
        }),
      )
      const start = startRun('x')
      const read = getRun(RUN_ID)
      await vi.advanceTimersByTimeAsync(16_000)
      expect(aborted).toEqual([`/api/requirement-interpretation/runs/${RUN_ID}`])
      expect(await read).toEqual({ ok: false, error: { kind: 'timeout' } })
      await vi.advanceTimersByTimeAsync(30_000)
      expect(aborted).toHaveLength(2)
      expect(await start).toEqual({ ok: false, error: { kind: 'timeout' } })
    } finally {
      vi.useRealTimers()
    }
  })
})
