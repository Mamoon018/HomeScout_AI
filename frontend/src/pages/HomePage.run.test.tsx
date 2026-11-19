import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

import { HomePage } from '@/pages/HomePage'
import { BODY, RUN_FAILED_BODY, RUN_ID, dropNulls } from '@/test/fixtures/r1Bodies'
import { PLAN } from '@/test/fixtures/r1Plan'
import { LONG_BRIEF, mockRunApi, type Call, type Reply } from '@/test/r1Server'

const TEXTAREA_NAME = 'Describe your ideal neighborhood and paste the address you want evaluated…'
/** The intro (heading fade, composer move) is real time; leave room for it. */
const SLOW = { timeout: 5000 }
const PLAN_HEADING = { name: "What I'll look for" }
const ANSWERS_PATH = `/${RUN_ID}/clarification-answers`

function typeBrief(text: string) {
  fireEvent.change(screen.getByRole('textbox', { name: TEXTAREA_NAME }), { target: { value: text } })
}

function sendBrief(text = LONG_BRIEF) {
  typeBrief(text)
  fireEvent.submit(screen.getByRole('form', { name: 'Neighborhood brief' }))
}

async function answerTheQuestion(option = 'a private balcony or loggia') {
  fireEvent.click(await screen.findByRole('radio', { name: option }, SLOW))
  fireEvent.click(screen.getByRole('button', { name: 'Submit' }))
}

/** Routes by method and path; a handler returns the reply for that call. */
function api(routes: Record<string, (call: Call) => Reply | Promise<Reply>>) {
  return mockRunApi((call) => {
    const key = `${call.method} ${call.path}`
    const route = routes[key]
    if (!route) {
      throw new Error(`Unexpected call: ${key}`)
    }
    return route(call)
  })
}

const ok = (body: unknown, status = 200): Reply => ({ status, body })

beforeEach(() => {
  window.sessionStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  window.sessionStorage.clear()
})

describe('composer', () => {
  it('holds Send back until the brief has 100 words and says how far along it is', () => {
    api({})
    render(<HomePage message="Welcome!" />)

    typeBrief('Quiet street near a park')
    expect(screen.getByText(/5 of 100 words/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()

    typeBrief(LONG_BRIEF)
    expect(screen.getByText('120 words')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled()
  })

  it("shows the server's reason under the composer and clears it when the renter edits", async () => {
    api({
      'POST /': () =>
        ok({ error: 'Instructions must be written in English' }, 422),
    })
    render(<HomePage message="Welcome!" />)
    sendBrief()

    expect(
      await screen.findByText(
        'HomeScout reads briefs written in English for now. Please write yours in English.',
        {},
        SLOW,
      ),
    ).toBeInTheDocument()
    // Nothing was started: no breakdown, and the renter can fix the brief and send again.
    expect(screen.queryByRole('heading', { name: 'Instructions decoded' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled()

    typeBrief(`${LONG_BRIEF} again`)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('a run that asks a question', () => {
  it('waits on the server, then shows the breakdown and the question, then the plan', async () => {
    let release: (reply: Reply) => void = () => {}
    const { calls } = api({
      'POST /': () => new Promise<Reply>((resolve) => (release = resolve)),
      [`POST ${ANSWERS_PATH}`]: () => ok(BODY.finished),
    })
    render(<HomePage message="Welcome!" />)
    sendBrief()

    // Nothing is known yet: the page says what it is waiting on and shows no data.
    await screen.findByRole('heading', { name: 'Instructions decoded' }, SLOW)
    expect(screen.getAllByText('Reading your brief.').length).toBeGreaterThan(0)
    expect(screen.queryByRole('region', { name: 'User Persona' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()

    release(ok(BODY.paused, 201))
    expect(await screen.findByRole('region', { name: 'User Persona' }, SLOW)).toBeInTheDocument()
    expect(screen.getByText('relocating to Munich in February')).toBeInTheDocument()
    expect(screen.getByText('Needs one answer from you')).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Clarification questions' })).toBeInTheDocument()

    await answerTheQuestion()
    const categories = await screen.findByRole('list', { name: 'Categories' }, SLOW)
    expect(within(categories).getByText('Transit station')).toBeInTheDocument()
    expect(screen.getByRole('heading', PLAN_HEADING)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled()

    // The answer goes over without a description: only "other" takes one.
    const sent = calls.find((c) => c.path === ANSWERS_PATH)
    expect(sent?.body).toEqual({ answers: [{ category_id: 7, option: 1 }] })
  })

  it('sends the renter\'s own words when they choose "other"', async () => {
    const { calls } = api({
      'POST /': () => ok(BODY.paused, 201),
      [`POST ${ANSWERS_PATH}`]: () => ok(BODY.finished),
    })
    render(<HomePage message="Welcome!" />)
    sendBrief()

    fireEvent.click(await screen.findByRole('radio', { name: 'Other' }, SLOW))
    fireEvent.change(screen.getByRole('textbox', { name: /Say what you meant/ }), {
      target: { value: 'a sunny roof' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }))

    await screen.findByRole('list', { name: 'Categories' }, SLOW)
    expect(calls.find((c) => c.path === ANSWERS_PATH)?.body).toEqual({
      answers: [{ category_id: 7, option: 5, description: 'a sunny roof' }],
    })
  })

  it('stays on the question and says why when the server refuses the answers', async () => {
    api({
      'POST /': () => ok(BODY.paused, 201),
      [`POST ${ANSWERS_PATH}`]: () => ok({ error: 'Answers must cover each question' }, 422),
    })
    render(<HomePage message="Welcome!" />)
    sendBrief()
    await answerTheQuestion()

    expect(
      await screen.findByText("Those answers didn't match the questions. Check them and try again."),
    ).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Clarification questions' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Submit' })).toBeEnabled()
  })
})

describe('a run that needs no question', () => {
  it('shows the breakdown and the plan from one response, and unlocks the composer', async () => {
    api({ 'POST /': () => ok(BODY.finished, 201) })
    render(<HomePage message="Welcome!" />)
    sendBrief()

    expect(await screen.findByRole('list', { name: 'Categories' }, SLOW)).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: TEXTAREA_NAME })).toHaveValue(LONG_BRIEF)
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled()
    expect(screen.queryByRole('form', { name: 'Clarification questions' })).not.toBeInTheDocument()
  })

  it('says so, in place, when there is nothing to show for a section', async () => {
    api({
      'POST /': () =>
        ok(
          {
            ...BODY.finished,
            user_requirements_structured: {
              explicit_categories: [],
              ambiguity_flags: [],
              persona_facts: [],
            },
            result: [],
          },
          201,
        ),
    })
    render(<HomePage message="Welcome!" />)
    sendBrief()

    expect(
      await screen.findByText("You didn't say anything about yourself, so I'm not assuming anything.", {}, SLOW),
    ).toBeInTheDocument()
    expect(screen.getByText('Everything you wrote was clear.')).toBeInTheDocument()
    expect(screen.getByText("I didn't find a place or feature in your brief.")).toBeInTheDocument()
    expect(screen.getByText(/There are no places to look for yet/)).toBeInTheDocument()
  })
})

describe('when a call does not give a run', () => {
  it('offers Retry after a failed step, then only Start again once the retry is used', async () => {
    const { calls } = api({
      'POST /': () => ok(BODY.paused, 201),
      [`POST ${ANSWERS_PATH}`]: () => ok(RUN_FAILED_BODY(true), 503),
      [`POST /${RUN_ID}/retry`]: () => ok(RUN_FAILED_BODY(false), 502),
      'GET /': () => ok({}, 404),
    })
    render(<HomePage message="Welcome!" />)
    sendBrief()
    await answerTheQuestion()

    const notice = await screen.findByRole('alert', {}, SLOW)
    expect(within(notice).getByText("Deciding what to look for didn't finish")).toBeInTheDocument()
    // What the run finished is still on screen.
    expect(screen.getByRole('region', { name: 'User Persona' })).toBeInTheDocument()

    fireEvent.click(within(notice).getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText("This run can't continue")).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()

    // Start again sends the same brief as a new run.
    const startsBefore = calls.filter((c) => c.method === 'POST' && c.path === '/').length
    fireEvent.click(screen.getByRole('button', { name: 'Start again' }))
    await waitFor(() =>
      expect(calls.filter((c) => c.method === 'POST' && c.path === '/')).toHaveLength(startsBefore + 1),
    )
    expect(calls.filter((c) => c.path === '/').at(-1)?.body).toEqual({ requirements: LONG_BRIEF })
  })

  it('finishes the plan when Retry succeeds', async () => {
    api({
      'POST /': () => ok(BODY.paused, 201),
      [`POST ${ANSWERS_PATH}`]: () => ok(RUN_FAILED_BODY(true), 503),
      [`POST /${RUN_ID}/retry`]: () => ok(BODY.finished),
    })
    render(<HomePage message="Welcome!" />)
    sendBrief()
    await answerTheQuestion()
    fireEvent.click(await screen.findByRole('button', { name: 'Retry' }, SLOW))

    expect(await screen.findByRole('list', { name: 'Categories' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('reads the run again when the answers call is lost, instead of guessing', async () => {
    const { calls } = api({
      'POST /': () => ok(BODY.paused, 201),
      [`POST ${ANSWERS_PATH}`]: () => 'network-error',
      [`GET /${RUN_ID}`]: () => ok(BODY.finished),
    })
    render(<HomePage message="Welcome!" />)
    sendBrief()
    await answerTheQuestion()

    // The server may have finished the run anyway: the page shows what it really did.
    expect(await screen.findByRole('list', { name: 'Categories' }, SLOW)).toBeInTheDocument()
    expect(calls.map((c) => `${c.method} ${c.path}`)).toContain(`GET /${RUN_ID}`)
  })

  it('shows where the run really is after a conflict', async () => {
    api({
      'POST /': () => ok(BODY.paused, 201),
      [`POST ${ANSWERS_PATH}`]: () =>
        ok({ error: 'The run is not waiting for answers', run_id: RUN_ID, status: 'finished' }, 409),
      [`GET /${RUN_ID}`]: () => ok(BODY.finished),
    })
    render(<HomePage message="Welcome!" />)
    sendBrief()
    await answerTheQuestion()

    expect(await screen.findByRole('list', { name: 'Categories' }, SLOW)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('sends the brief again with Try again when nothing could be created', async () => {
    let attempts = 0
    const { calls } = api({
      'POST /': () => (++attempts === 1 ? 'network-error' : ok(BODY.finished, 201)),
    })
    render(<HomePage message="Welcome!" />)
    sendBrief()

    const notice = await screen.findByRole('alert', {}, SLOW)
    expect(within(notice).getByText("Couldn't reach HomeScout")).toBeInTheDocument()
    expect(within(notice).getByText(/Your brief is still in the box/)).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: TEXTAREA_NAME })).toHaveValue(LONG_BRIEF)

    fireEvent.click(within(notice).getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('list', { name: 'Categories' }, SLOW)).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST' && c.path === '/')).toHaveLength(2)
  })

  it('shows the extraction a failed run saved, found through the status endpoint', async () => {
    api({
      'POST /': () => ok(RUN_FAILED_BODY(true), 503),
      [`GET /${RUN_ID}`]: () => ok(BODY.failed(true)),
    })
    render(<HomePage message="Welcome!" />)
    sendBrief()

    expect(await screen.findByRole('region', { name: 'User Persona' }, SLOW)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('sends the renter to sign in when the session is gone', async () => {
    const onUnauthenticated = vi.fn()
    api({ 'POST /': () => ok({ error: 'Not authenticated' }, 401) })
    render(<HomePage message="Welcome!" onUnauthenticated={onUnauthenticated} />)
    sendBrief()

    await waitFor(() => expect(onUnauthenticated).toHaveBeenCalledTimes(1), SLOW)
  })
})

describe('coming back to a run after a refresh', () => {
  beforeEach(() => {
    window.sessionStorage.setItem('homescout.r1.runId', RUN_ID)
  })

  it('shows a run that is waiting for answers, with its question', async () => {
    api({ [`GET /${RUN_ID}`]: () => ok(BODY.paused) })
    render(<HomePage message="Welcome!" />)

    expect(await screen.findByRole('form', { name: 'Clarification questions' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'User Persona' })).toBeInTheDocument()
    // The heading and the composer are already where they move to on a first run.
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
  })

  it('shows a finished run, and what each flagged phrase became', async () => {
    api({
      [`GET /${RUN_ID}`]: () =>
        ok({
          ...BODY.finished,
          result: [...dropNulls(PLAN), { category_id: 7, taxonomy_node: 'balcony', depth: 'basic_profile' }],
        }),
    })
    render(<HomePage message="Welcome!" />)

    expect(await screen.findByRole('list', { name: 'Categories' })).toBeInTheDocument()
    // No answers are held after a refresh, so the plan says what the flagged phrase became.
    const unsure = screen.getByRole('region', { name: 'Not sure yet' })
    expect(within(unsure).getByText('Balcony')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
  })

  it('shows a stopped run with the ways on that its status allows', async () => {
    api({ [`GET /${RUN_ID}`]: () => ok(BODY.failed(false)) })
    render(<HomePage message="Welcome!" />)

    expect(await screen.findByText("This run can't continue")).toBeInTheDocument()
    // The brief is not known after a refresh, so there is nothing to send again.
    expect(screen.getByRole('button', { name: 'Write a new brief' })).toBeInTheDocument()
  })

  it('keeps reading a run that is still working until it settles', async () => {
    let reads = 0
    api({ [`GET /${RUN_ID}`]: () => (++reads < 2 ? ok(BODY.running) : ok(BODY.paused)) })
    render(<HomePage message="Welcome!" />)

    expect(await screen.findAllByText('Picking up where you left off.')).not.toHaveLength(0)
    expect(
      await screen.findByRole('form', { name: 'Clarification questions' }, { timeout: 6000 }),
    ).toBeInTheDocument()
    expect(reads).toBe(2)
  }, 10_000)

  it('says the run is gone, and forgets it, when the server has no such run', async () => {
    api({ [`GET /${RUN_ID}`]: () => ok({ error: 'Run not found' }, 404) })
    render(<HomePage message="Welcome!" />)

    expect(await screen.findByText('That run is no longer available')).toBeInTheDocument()
    expect(window.sessionStorage.getItem('homescout.r1.runId')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Write a new brief' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Instructions decoded' })).not.toBeInTheDocument()
  })

  it('offers Try again when the saved run cannot be reached, and loads it then', async () => {
    let up = false
    api({ [`GET /${RUN_ID}`]: () => (up ? ok(BODY.finished) : { status: 503, body: { error: 'Run storage is unavailable' } }) })
    render(<HomePage message="Welcome!" />)

    expect(await screen.findByText("Couldn't reach HomeScout")).toBeInTheDocument()
    expect(screen.getByText(/Your run is saved/)).toBeInTheDocument()

    up = true
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('list', { name: 'Categories' })).toBeInTheDocument()
  })
})
