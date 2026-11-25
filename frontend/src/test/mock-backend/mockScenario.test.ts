import { idsFor, parseMockId } from '@/mocks/mockRunIds'
import { SCENARIOS, readScenario } from '@/mocks/mockScenario'

describe('readScenario', () => {
  afterEach(() => vi.restoreAllMocks())

  it('defaults to happy when ?mock= is absent or empty', () => {
    expect(readScenario('')).toBe('happy')
    expect(readScenario('?mock=')).toBe('happy')
  })

  it('returns every known scenario by name', () => {
    for (const name of SCENARIOS) expect(readScenario(`?mock=${name}`)).toBe(name)
  })

  it('falls back to happy and warns mock_unknown_scenario for an unknown name', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(readScenario('?mock=sideways')).toBe('happy')
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('[mock_unknown_scenario]'))
  })
})

describe('fixed run ids', () => {
  it('gives each scenario one id per stage', () => {
    expect(idsFor('error')).toEqual({ r1: 'mock_error_r1', r2: 'mock_error_r2', r3: 'mock_error_r3' })
  })

  it('reads the scenario and stage back from an id, including hyphenated names', () => {
    expect(parseMockId('mock_not-found_r3')).toEqual({ scenario: 'not-found', stage: 'r3' })
  })

  it('rejects ids that are not in the table', () => {
    expect(parseMockId('mock_sideways_r1')).toBeNull()
    expect(parseMockId('mock_happy_r4')).toBeNull()
    expect(parseMockId('3f2b8c1e-0000-4000-8000-000000000000')).toBeNull()
  })
})
