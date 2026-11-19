import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

import { saveR2Run } from '@/features/r2-proximity/utils/runStorage'
import { PlacesMetricsPage } from '@/pages/PlacesMetricsPage'
import {
  R1_FINISHED,
  R1_FINISHED_B,
  R1_RUN_ID,
  R1_RUN_ID_B,
  R2_FINISHED,
  R2_FINISHED_B,
  R2_RUN_ID,
  R2_RUN_ID_B,
  R3_BODY,
  R3_ERROR,
  R3_RUN_ID,
  R3_RUN_ID_B,
} from '@/test/fixtures/r3Bodies'
import type { Reply } from '@/test/r1Server'
import { mockR3Api, type R3Call } from '@/test/r3Server'

/** One poll interval (4 s) plus room. */
const POLL = { timeout: 8000 }
const ok = (body: unknown, status = 200): Reply => ({ status, body })
type Routes = Record<string, (call: R3Call) => Reply | Promise<Reply>>

/** The R1 and R2 reads a finished run is joined with. */
const CONTEXT: Routes = {
  [`r2 GET /${R2_RUN_ID}`]: () => ok(R2_FINISHED),
  [`r1 GET /${R1_RUN_ID}`]: () => ok(R1_FINISHED),
}

function rememberAmenitySearch() {
  saveR2Run({ runId: R2_RUN_ID, r1RunId: R1_RUN_ID, latitude: 52.3676, longitude: 4.9041, radiusKm: 2 })
}

/** A run is opened from the address bar; its body names its own parents. */
const RUN_URL = `/places_metrics?run=${R3_RUN_ID}`

/** Shows the address bar's query, so a test can see what the page put there. */
function LocationProbe() {
  return <output data-testid="location">{useLocation().search}</output>
}

function renderPage(url = '/places_metrics', onUnauthenticated = vi.fn()) {
  render(
    <MemoryRouter initialEntries={[url]}>
      <PlacesMetricsPage onUnauthenticated={onUnauthenticated} />
      <LocationProbe />
    </MemoryRouter>,
  )
  return onUnauthenticated
}

/** What a tab holds after it also ran brief B: every storage slot points at B. */
function rememberRunB() {
  saveR2Run({ runId: R2_RUN_ID_B, r1RunId: R1_RUN_ID_B, latitude: 48.1374, longitude: 11.5755, radiusKm: 2 })
  window.sessionStorage.setItem('homescout.r1.runId', R1_RUN_ID_B)
  window.sessionStorage.setItem('homescout.r3.run', JSON.stringify({ runId: R3_RUN_ID_B, r2RunId: R2_RUN_ID_B }))
}

/** Both chains are served, so a wrong lookup would show B's data instead of failing. */
const BOTH_CHAINS: Routes = {
  [`r3 GET /${R3_RUN_ID}`]: () => ok(R3_BODY.finished),
  ...CONTEXT,
  [`r3 GET /${R3_RUN_ID_B}`]: () => ok({ ...R3_BODY.finished, run_id: R3_RUN_ID_B, r2_run_id: R2_RUN_ID_B }),
  [`r2 GET /${R2_RUN_ID_B}`]: () => ok(R2_FINISHED_B),
  [`r1 GET /${R1_RUN_ID_B}`]: () => ok(R1_FINISHED_B),
}

/** A's page: A's places, A's origin, and A's brief (the museum was inferred, so it is "also worth knowing"). */
async function expectRunA(calls: string[]) {
  const table = await screen.findByRole('table', { name: 'Gym: your needs by place' })
  expect(within(table).getByRole('button', { name: 'Iron Yard Strength, open its proof' })).toBeInTheDocument()
  expect(screen.getByText(/Near 52\.3676, 4\.9041/)).toBeInTheDocument()
  expect(screen.queryByText(/Bravo/)).not.toBeInTheDocument()
  expect(screen.queryByText(/48\.1374/)).not.toBeInTheDocument()
  fireEvent.click(within(screen.getByRole('navigation', { name: 'All places' })).getByRole('button', { name: /^Museum/ }))
  fireEvent.click(screen.getByRole('button', { name: /^Herengracht Print Museum,/ }))
  expect(screen.getByRole('heading', { name: /Also worth knowing/ })).toBeInTheDocument()
  expect(calls.filter((c) => c.includes('bb'))).toEqual([])
}

beforeEach(() => window.sessionStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  window.sessionStorage.clear()
})

describe('before a run', () => {
  it('points to the places page when this tab has no amenity search, and calls nothing', () => {
    const { calls } = mockR3Api({})
    renderPage()
    expect(screen.getByRole('heading', { name: 'Start from your places' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to places' })).toHaveAttribute('href', '/proximity_info')
    expect(calls).toHaveLength(0)
  })

  it('starts with exactly the contract body and shows the first progress step', async () => {
    rememberAmenitySearch()
    const { calls, bodies } = mockR3Api({ 'r3 POST /': () => ok(R3_BODY.running, 202), [`r3 GET /${R3_RUN_ID}`]: () => ok(R3_BODY.running) })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Check my questions' }))
    expect(await screen.findByRole('heading', { name: 'Checking your questions' })).toBeInTheDocument()
    expect(calls[0]).toBe('r3 POST /')
    expect(bodies[0]).toEqual({ r2_run_id: R2_RUN_ID })
    expect(screen.getByText(/Finding each place’s own website/)).toHaveTextContent('(in progress)')
    // The address bar is the run's only copy; nothing is written to tab storage.
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(`?run=${R3_RUN_ID}`))
    expect(window.sessionStorage.getItem('homescout.r3.run')).toBeNull()
  })

  it('explains a start refused because the amenity search is not finished (404)', async () => {
    rememberAmenitySearch()
    mockR3Api({ 'r3 POST /': () => ok(R3_ERROR.r2NotFound, 404) })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Check my questions' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/hasn’t finished/)
    expect(within(screen.getByRole('alert')).getByRole('link', { name: 'Go to places' })).toBeInTheDocument()
  })

  it('offers Try again when the start call fails, and it calls start again', async () => {
    rememberAmenitySearch()
    let n = 0
    const { calls } = mockR3Api({
      'r3 POST /': () => (n++ === 0 ? 'network-error' : ok(R3_BODY.running, 202)),
      [`r3 GET /${R3_RUN_ID}`]: () => ok(R3_BODY.running),
    })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Check my questions' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'Checking your questions' })).toBeInTheDocument()
    expect(calls.filter((c) => c === 'r3 POST /')).toHaveLength(2)
  })
})

describe('while it runs', () => {
  it('restores a run from the address bar after a refresh, with nothing stored', async () => {
    mockR3Api({ [`r3 GET /${R3_RUN_ID}`]: () => ok(R3_BODY.researching) })
    renderPage(RUN_URL)
    expect(await screen.findByText(/Researching your questions/)).toHaveTextContent('(in progress)')
    expect(screen.getByText(/Finding each place’s own website/)).toHaveTextContent('(done)')
  })

  it('polls until finished, then shows the results', async () => {
    let reads = 0
    mockR3Api({
      [`r3 GET /${R3_RUN_ID}`]: () => ok(reads++ === 0 ? R3_BODY.running : R3_BODY.finished),
      ...CONTEXT,
    })
    renderPage(RUN_URL)
    expect(await screen.findByRole('heading', { name: 'Checking your questions' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Do nearby places really fit?' }, POLL)).toBeInTheDocument()
  }, 12000)
})

describe('the finished result', () => {
  async function showFinished() {
    const api = mockR3Api({ [`r3 GET /${R3_RUN_ID}`]: () => ok(R3_BODY.finished), ...CONTEXT })
    renderPage(RUN_URL)
    await screen.findByRole('heading', { name: 'Do nearby places really fit?' })
    return api
  }

  it('names places from R2 and questions from R1, and skips categories with no questions', async () => {
    await showFinished()
    const table = screen.getByRole('table', { name: 'Gym: your needs by place' })
    expect(within(table).getByRole('button', { name: 'Iron Yard Strength, open its proof' })).toBeInTheDocument()
    expect(within(table).getByText('Powerlifting platform')).toBeInTheDocument()
    // A snake_case label reads as words.
    expect(within(table).getByText('Evening crowding')).toBeInTheDocument()
    expect(screen.queryByText(/Transit station/)).not.toBeInTheDocument()
    expect(screen.getByText(/Near 52\.3676, 4\.9041/)).toBeInTheDocument()
    expect(screen.getByText('Finished · checked 14 Nov')).toBeInTheDocument()
  })

  it('maps each answer: yes fits, no is missing, mixed leans, unconfirmed says why', async () => {
    await showFinished()
    const table = screen.getByRole('table', { name: 'Gym: your needs by place' })
    const rowOf = (name: string) => within(table).getByRole('button', { name: `${name}, open its proof` }).closest('[role="row"]') as HTMLElement
    expect(within(rowOf('Iron Yard Strength')).getByText('Fits all')).toBeInTheDocument()
    expect(within(rowOf('Canal Fitness')).getByText('No')).toBeInTheDocument()
    expect(within(rowOf('Canal Fitness')).getByText('Leans busy')).toBeInTheDocument()
    const plant = rowOf('Plantage Fit')
    expect(within(plant).getByText('search failed')).toBeInTheDocument()
    expect(within(plant).getByText('mentions only · not enough')).toBeInTheDocument()
    // Nothing confirmed at all: both cells and the fit pill read "No info".
    expect(within(plant).getAllByText('No info')).toHaveLength(3)
    // No walking route: said, not invented.
    expect(within(plant).getByText(/no walk route/)).toBeInTheDocument()
  })

  it('opens the best fit’s proof with real source links', async () => {
    await showFinished()
    const proof = screen.getByRole('region', { name: /^Iron Yard Strength:/ })
    expect(within(proof).getByRole('link', { name: 'Website: ironyard-strength.nl' })).toHaveAttribute('href', 'https://www.ironyard-strength.nl/')
    expect(within(proof).getByRole('link', { name: 'ironyard-strength.nl' })).toHaveAttribute('target', '_blank')
    fireEvent.click(within(proof).getByRole('button', { name: /Evening crowding/ }))
    expect(within(proof).getByText('Google reviews · 1')).toBeInTheDocument()
    expect(within(proof).getByText(/Busy-ish around 6, never packed\./)).toBeInTheDocument()
  })

  it('shows an inferred category after the asked one, with currency and an unmet verification', async () => {
    await showFinished()
    fireEvent.click(within(screen.getByRole('navigation', { name: 'All places' })).getByRole('button', { name: /^Museum/ }))
    fireEvent.click(screen.getByRole('button', { name: /^Herengracht Print Museum,/ }))
    expect(screen.getByRole('heading', { name: /Also worth knowing/ })).toBeInTheDocument()
    const table = screen.getByRole('table', { name: 'Museum: your needs by place' })
    expect(within(table).getByText('€17.50')).toBeInTheDocument()
    expect(within(table).getByText('Leans €25')).toBeInTheDocument()
    const proof = screen.getByRole('region', { name: /^Herengracht Print Museum:/ })
    expect(within(proof).getByText('I found mentions, but not enough to be sure.')).toBeInTheDocument()
  })

  it('holds the result when the questions (R1) cannot be loaded, and Try again loads them', async () => {
    let r1 = 0
    mockR3Api({
      [`r3 GET /${R3_RUN_ID}`]: () => ok(R3_BODY.finished),
      [`r2 GET /${R2_RUN_ID}`]: () => ok(R2_FINISHED),
      [`r1 GET /${R1_RUN_ID}`]: () => (r1++ === 0 ? ok(R3_ERROR.storeDown, 503) : ok(R1_FINISHED)),
    })
    renderPage(RUN_URL)
    // Strict: no result with differently worded questions, and no silent downgrade.
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t load its places and questions/)
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('table', { name: 'Gym: your needs by place' })).toBeInTheDocument()
  })

  it('says when the places cannot be loaded, and Try again loads them', async () => {
    let r2 = 0
    mockR3Api({
      [`r3 GET /${R3_RUN_ID}`]: () => ok(R3_BODY.finished),
      [`r2 GET /${R2_RUN_ID}`]: () => (r2++ === 0 ? ok(R3_ERROR.storeDown, 503) : ok(R2_FINISHED)),
      [`r1 GET /${R1_RUN_ID}`]: () => ok(R1_FINISHED),
    })
    renderPage(RUN_URL)
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t load its places/)
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'Do nearby places really fit?' })).toBeInTheDocument()
  })

  it('shows a calm empty state when nothing had questions', async () => {
    mockR3Api({ [`r3 GET /${R3_RUN_ID}`]: () => ok(R3_BODY.finishedEmpty), ...CONTEXT })
    renderPage(RUN_URL)
    expect(await screen.findByRole('heading', { name: 'Nothing specific to check' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'See places and travel times' })).toHaveAttribute('href', '/proximity_info')
  })
})

describe('failures', () => {
  it('offers Retry for a retryable failure, and a retry resumes the run', async () => {
    const { calls } = mockR3Api({
      [`r3 GET /${R3_RUN_ID}`]: () => ok(R3_BODY.failed(true)),
      [`r3 POST /${R3_RUN_ID}/retry`]: () => ok(R3_BODY.researching, 202),
    })
    renderPage(RUN_URL)
    expect(await screen.findByRole('alert')).toHaveTextContent(/stopped partway/)
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText(/Researching your questions/)).toHaveTextContent('(in progress)')
    expect(calls).toContain(`r3 POST /${R3_RUN_ID}/retry`)
  })

  it('on a retry conflict, re-reads the run and shows what it now allows', async () => {
    let reads = 0
    mockR3Api({
      [`r3 GET /${R3_RUN_ID}`]: () => ok(R3_BODY.failed(reads++ === 0)),
      [`r3 POST /${R3_RUN_ID}/retry`]: () => ok(R3_ERROR.conflict('failed', false), 409),
    })
    renderPage(RUN_URL)
    fireEvent.click(await screen.findByRole('button', { name: 'Retry' }))
    expect(await screen.findByText(/can’t be resumed/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
  })

  it('Start again on a final failure returns to the start and forgets the run', async () => {
    rememberAmenitySearch() // the start panel offers a new check from this tab's places
    mockR3Api({ [`r3 GET /${R3_RUN_ID}`]: () => ok(R3_BODY.failed(false)) })
    renderPage(RUN_URL)
    fireEvent.click(await screen.findByRole('button', { name: 'Start again' }))
    expect(screen.getByRole('button', { name: 'Check my questions' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(/^$/)
  })

  it('a run that no longer exists resets to the start (404)', async () => {
    rememberAmenitySearch() // the start panel offers a new check from this tab's places
    mockR3Api({ [`r3 GET /${R3_RUN_ID}`]: () => ok(R3_ERROR.notFound, 404) })
    renderPage(RUN_URL)
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t find that check/)
    expect(screen.getByRole('button', { name: 'Check my questions' })).toBeInTheDocument()
  })

  it('hands an expired session to the app (401)', async () => {
    mockR3Api({ [`r3 GET /${R3_RUN_ID}`]: () => ok(R3_ERROR.unauthenticated, 401) })
    const onUnauthenticated = renderPage(RUN_URL)
    await waitFor(() => expect(onUnauthenticated).toHaveBeenCalled())
  })
})

describe('the run chain', () => {
  it('a new tab (storage empty) shows A’s own places, origin and brief', async () => {
    const { calls } = mockR3Api(BOTH_CHAINS)
    renderPage(RUN_URL)
    await expectRunA(calls)
    expect(calls).toEqual([`r3 GET /${R3_RUN_ID}`, `r2 GET /${R2_RUN_ID}`, `r1 GET /${R1_RUN_ID}`])
  })

  it('A after B in the same tab: B’s stored runs never reach A’s page', async () => {
    rememberRunB()
    const { calls } = mockR3Api(BOTH_CHAINS)
    renderPage(RUN_URL)
    await expectRunA(calls)
  })

  it('all match (control): A stored and opened shows the same page', async () => {
    rememberAmenitySearch()
    window.sessionStorage.setItem('homescout.r1.runId', R1_RUN_ID)
    const { calls } = mockR3Api(BOTH_CHAINS)
    renderPage(RUN_URL)
    await expectRunA(calls)
  })

  it('stops with a notice when the R3 body names no R2 run, and calls nothing more', async () => {
    rememberAmenitySearch()
    const { calls } = mockR3Api({
      ...BOTH_CHAINS,
      [`r3 GET /${R3_RUN_ID}`]: () => ok({ ...R3_BODY.finished, r2_run_id: undefined }),
    })
    renderPage(RUN_URL)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/couldn’t tell which amenity search/)
    expect(within(alert).getByRole('link', { name: 'Go to places' })).toHaveAttribute('href', '/proximity_info')
    expect(within(alert).queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Checking your questions' })).not.toBeInTheDocument()
    expect(calls).toEqual([`r3 GET /${R3_RUN_ID}`])
  })

  it('stops with a notice when the R2 body names no R1 run, and never guesses one', async () => {
    window.sessionStorage.setItem('homescout.r1.runId', R1_RUN_ID_B)
    const { calls } = mockR3Api({
      ...BOTH_CHAINS,
      [`r2 GET /${R2_RUN_ID}`]: () => ok({ ...R2_FINISHED, r1_run_id: undefined }),
    })
    renderPage(RUN_URL)
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t tell which amenity search/)
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(calls).toEqual([`r3 GET /${R3_RUN_ID}`, `r2 GET /${R2_RUN_ID}`])
  })

  it('drops a late reply for a run the page has left: no next step is requested', async () => {
    let releaseR2: (reply: Reply) => void = () => {}
    const { calls } = mockR3Api({
      ...BOTH_CHAINS,
      [`r2 GET /${R2_RUN_ID}`]: () => new Promise<Reply>((resolve) => (releaseR2 = resolve)),
    })
    const { unmount } = renderWithUnmount(RUN_URL)
    await waitFor(() => expect(calls).toContain(`r2 GET /${R2_RUN_ID}`))
    unmount()
    releaseR2(ok(R2_FINISHED))
    await new Promise((r) => setTimeout(r, 50))
    expect(calls).not.toContain(`r1 GET /${R1_RUN_ID}`)
  })

  it('opening the page without ?run= starts clean, even with an old stored run', async () => {
    rememberAmenitySearch()
    window.sessionStorage.setItem('homescout.r3.run', JSON.stringify({ runId: R3_RUN_ID, r2RunId: R2_RUN_ID }))
    const { calls } = mockR3Api({})
    renderPage()
    expect(screen.getByRole('button', { name: 'Check my questions' })).toBeInTheDocument()
    expect(calls).toHaveLength(0)
  })
})

function renderWithUnmount(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <PlacesMetricsPage onUnauthenticated={vi.fn()} />
    </MemoryRouter>,
  )
}
