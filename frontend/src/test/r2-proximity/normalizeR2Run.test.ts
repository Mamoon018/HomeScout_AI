import type { R2RunWire } from '@/features/r2-proximity/types/r2'
import { normalizeR2Run } from '@/features/r2-proximity/utils/normalizeR2Run'
import { R1_RUN_ID, R2_BODY } from '@/mocks/fixtures/r2Bodies'

const radiusOf = (radius_km: unknown) =>
  normalizeR2Run({ ...R2_BODY.running, radius_km } as unknown as R2RunWire)?.radiusKm

describe('normalizeR2Run: the run context every response carries', () => {
  it('reads the R1 run, origin and radius from a running body', () => {
    expect(normalizeR2Run(R2_BODY.running as R2RunWire)).toMatchObject({
      r1RunId: R1_RUN_ID,
      origin: { latitude: 50.1109, longitude: 8.6821 },
      radiusKm: 2,
    })
  })

  it.each([
    ['a missing', undefined],
    ['a zero', 0],
    ['a negative', -1],
    ['a non-finite', Number.POSITIVE_INFINITY],
    ['a text', '2'],
  ])('turns %s radius into null', (_, radius) => {
    expect(radiusOf(radius)).toBeNull()
  })

  it('keeps a fractional radius', () => {
    expect(radiusOf(1.5)).toBe(1.5)
  })
})
