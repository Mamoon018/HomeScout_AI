import { normalizeRun } from '@/features/r1-interpretation/utils/normalizeRun'
import type { RunWire } from '@/features/r1-interpretation/types/run'
import { BODY, RUN_ID } from '@/test/fixtures/r1Bodies'
import { EXTRACTION } from '@/test/fixtures/r1Extraction'
import { PLAN } from '@/test/fixtures/r1Plan'

const wire = (body: unknown) => body as RunWire

describe('normalizeRun', () => {
  it('turns the fields the backend leaves out into null or empty, so the UI reads one shape', () => {
    // The backend's body has no `category`, `characteristic` or `unit` keys where they were null.
    const view = normalizeRun(wire(BODY.finished))
    expect(view?.extraction?.ambiguity_flags[0]).toEqual({
      phrase: 'a balcony or small garden',
      target: 'category',
      category: null,
      category_id: 7,
      characteristic: null,
    })
    // The finished body, read back, equals the typed fixture the components were built against.
    expect(view?.extraction).toEqual(EXTRACTION)
    expect(view?.plan).toEqual(PLAN)
    expect(view?.retryable).toBeNull()
  })

  it('keeps questions only while paused and the plan only when finished', () => {
    const paused = normalizeRun(wire(BODY.paused))
    expect(paused?.questions).toHaveLength(1)
    expect(paused?.plan).toBeNull()

    const finished = normalizeRun(wire(BODY.finished))
    expect(finished?.questions).toEqual([])
    expect(finished?.plan?.length).toBeGreaterThan(0)
  })

  it('carries what a failed run saved, and whether Retry is left', () => {
    const withExtraction = normalizeRun(wire(BODY.failed(true)))
    expect(withExtraction?.status).toBe('failed')
    expect(withExtraction?.extraction?.explicit_categories.length).toBeGreaterThan(0)
    expect(withExtraction?.retryable).toBe(true)

    const early = normalizeRun(wire(BODY.failed(false, false)))
    expect(early?.extraction).toBeNull()
    expect(early?.retryable).toBe(false)
  })

  it('reads a running run as having nothing yet', () => {
    expect(normalizeRun(wire(BODY.running))).toEqual({
      runId: RUN_ID,
      status: 'running',
      extraction: null,
      questions: [],
      plan: null,
      retryable: null,
    })
  })

  it('fills empty lists and gives categories their list position when the id is missing', () => {
    const view = normalizeRun(
      wire({
        run_id: RUN_ID,
        status: 'finished',
        user_requirements_structured: {
          explicit_categories: [{ name: 'gym' }],
        },
        result: [{ category_id: 0, taxonomy_node: 'gym', depth: 'basic_profile' }],
      }),
    )
    expect(view?.extraction).toEqual({
      persona_facts: [],
      ambiguity_flags: [],
      explicit_categories: [{ name: 'gym', category_id: 0, characteristics: [] }],
    })
    expect(view?.plan?.[0]).toMatchObject({ predefined_metrics: [], specific_metrics: [] })
  })

  it('fills a missing unit, answers and sources of a check without inventing values', () => {
    const view = normalizeRun(
      wire({
        run_id: RUN_ID,
        status: 'finished',
        user_requirements_structured: {
          explicit_categories: [],
          ambiguity_flags: [],
          persona_facts: [],
        },
        result: [
          {
            category_id: 0,
            taxonomy_node: 'gym',
            depth: 'specific_attributes',
            specific_metrics: [
              {
                label: 'Wifi',
                question: 'Is there wifi?',
                value_type: 'boolean',
                evidence_class: 'factual',
                resolution_source: { web_target: 'gym wifi' },
                verification: 'listed',
                null_policy: 'unknown',
                band: 'specific_attributes',
              },
            ],
          },
        ],
      }),
    )
    expect(view?.plan?.[0].specific_metrics[0]).toMatchObject({
      unit: null,
      enum_values: [],
      resolution_source: { web_target: 'gym wifi', scrape_target: null, review_target: null },
    })
  })

  it.each([
    ['no body', null],
    ['no run id', { status: 'running' }],
    ['an unknown status', { run_id: RUN_ID, status: 'paused' }],
    ['a paused run without questions', { ...BODY.paused, questions: [] }],
    [
      'a paused run without its extraction',
      { ...BODY.paused, user_requirements_structured: undefined },
    ],
    ['a finished run without its plan', { ...BODY.finished, result: undefined }],
  ])('refuses %s, so the page never shows half a run', (_name, body) => {
    expect(normalizeRun(wire(body))).toBeNull()
  })
})
