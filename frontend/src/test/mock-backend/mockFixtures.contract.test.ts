/**
 * Fixture contract: every stored backend response, and every body the dev mock stamps with its
 * fixed ids, must still read through the real normalizers. A null means the fixture drifted from
 * the frontend's view of the backend contract (mock_fixture_invalid).
 */
import { normalizeRun } from '@/features/r1-interpretation/utils/normalizeRun'
import { normalizeR2Run } from '@/features/r2-proximity/utils/normalizeR2Run'
import type { R2RunWire } from '@/features/r2-proximity/types/r2'
import { normalizeR3Run } from '@/features/places-metrics/utils/normalizeR3Run'
import type { R3RunWire } from '@/features/places-metrics/types/r3Run'
import type { RunWire } from '@/features/r1-interpretation/types/run'
import { buildPlacesMetrics } from '@/features/places-metrics/utils/buildPlacesMetrics'
import { r1Body, r2Body, r3Body, type R1Kind, type R2Kind } from '@/mocks/fixtures/devStory'
import { BODY } from '@/mocks/fixtures/r1Bodies'
import { R2_BODY } from '@/mocks/fixtures/r2Bodies'
import { R1_FINISHED, R1_FINISHED_B, R2_FINISHED, R2_FINISHED_B, R3_BODY } from '@/mocks/fixtures/r3Bodies'

const r1 = (b: unknown) => normalizeRun(b as RunWire)
const r2 = (b: unknown) => normalizeR2Run(b as R2RunWire)
const r3 = (b: unknown) => normalizeR3Run(b as R3RunWire)

function expectValid(name: string, view: unknown) {
  expect(view, `mock_fixture_invalid: ${name} no longer normalizes`).not.toBeNull()
}

describe('stored fixtures', () => {
  it.each([
    ['BODY.running', BODY.running],
    ['BODY.paused', BODY.paused],
    ['BODY.finished', BODY.finished],
    ['BODY.failed', BODY.failed(true)],
    ['R1_FINISHED', R1_FINISHED],
    ['R1_FINISHED_B', R1_FINISHED_B],
  ])('R1 %s normalizes', (name, body) => expectValid(name, r1(body)))

  it.each([
    ['R2_BODY.running', R2_BODY.running],
    ['R2_BODY.runningAfterDiscovery', R2_BODY.runningAfterDiscovery],
    ['R2_BODY.finished', R2_BODY.finished],
    ['R2_BODY.finishedEmpty', R2_BODY.finishedEmpty],
    ['R2_BODY.finishedSparse', R2_BODY.finishedSparse],
    ['R2_BODY.failed', R2_BODY.failed(true)],
    ['R2_FINISHED', R2_FINISHED],
    ['R2_FINISHED_B', R2_FINISHED_B],
  ])('R2 %s normalizes', (name, body) => expectValid(name, r2(body)))

  it.each([
    ['R3_BODY.running', R3_BODY.running],
    ['R3_BODY.researching', R3_BODY.researching],
    ['R3_BODY.finished', R3_BODY.finished],
    ['R3_BODY.finishedEmpty', R3_BODY.finishedEmpty],
    ['R3_BODY.failed', R3_BODY.failed(true)],
  ])('R3 %s normalizes', (name, body) => expectValid(name, r3(body)))
})

describe('dev story, stamped with fixed ids', () => {
  const r1Kinds: R1Kind[] = ['running', 'needs_answers', 'finished', 'failed']
  const r2Kinds: R2Kind[] = ['running', 'progress', 'finished', 'finished_empty', 'failed']

  it.each(r1Kinds)('R1 %s normalizes and keeps the fixed id', (kind) => {
    expect(r1(r1Body(kind, 'mock_happy_r1'))).toMatchObject({ runId: 'mock_happy_r1' })
  })

  it.each(r2Kinds)('R2 %s normalizes and names its R1 run', (kind) => {
    expect(r2(r2Body(kind, 'mock_happy_r2', 'mock_happy_r1'))).toMatchObject({ runId: 'mock_happy_r2', r1RunId: 'mock_happy_r1' })
  })

  it.each(r2Kinds)('R3 %s normalizes and names its R2 run', (kind) => {
    expect(r3(r3Body(kind, 'mock_happy_r3', 'mock_happy_r2'))).toMatchObject({ runId: 'mock_happy_r3', r2RunId: 'mock_happy_r2' })
  })

  it('joins into one coherent places-metrics page: every row has its R2 place and R1 question', () => {
    const plan = r1(r1Body('finished', 'mock_happy_r1'))!
    const places = r2(r2Body('finished', 'mock_happy_r2', 'mock_happy_r1'))!
    const rows = r3(r3Body('finished', 'mock_happy_r3', 'mock_happy_r2'))!

    const page = buildPlacesMetrics(rows.result!, {
      plan: plan.plan,
      askedIds: new Set(plan.extraction!.explicit_categories.map((c) => c.category_id)),
      r2: places.result,
      origin: places.origin,
    })

    expect(page.categories.map((c) => c.key)).toEqual(['2', '3'])
    expect(page.places).toHaveLength(4)
    for (const place of page.places) {
      expect(place.name, `${place.key} has no R2 place`).not.toMatch(/^Place /)
      expect(Object.keys(place.answers).length, `${place.key} answers no R1 question`).toBeGreaterThan(0)
    }
  })
})
