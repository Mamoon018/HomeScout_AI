import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { saveRunId } from '@/features/r1-interpretation/utils/runStorage'
import { saveR2Run } from '@/features/r2-proximity/utils/runStorage'
import { ProximityPage } from '@/pages/ProximityPage'
import { BODY } from '@/test/fixtures/r1Bodies'
import { R1_RUN_ID, R2_BODY, R2_ERROR, R2_RUN_ID } from '@/test/fixtures/r2Bodies'
import { mockR2Api, type R2Call } from '@/test/r2Server'
import type { Reply } from '@/test/r1Server'

/** Polling is real time (2 s); leave room for one tick. */
const SLOW = { timeout: 6000 }
const SAVED = { runId: R2_RUN_ID, r1RunId: R1_RUN_ID, latitude: 50.1109, longitude: 8.6821, radiusKm: 2 }

type Routes = Record<string, (call: R2Call) => Reply | Promise<Reply>>
const ok = (body: unknown, status = 200): Reply => ({ status, body })

function api(routes: Routes) {
  return mockR2Api(
    (call) => {
      const route = routes[`${call.method} ${call.path}`]
      if (!route) throw new Error(`Unexpected call: ${call.method} ${call.path}`)
      return route(call)
    },
    () => ok(BODY.finished),
  )
}

function renderPage(url = '/proximity_info', onUnauthenticated = vi.fn()) {
  render(
    <MemoryRouter initialEntries={[url]}>
      <ProximityPage onUnauthenticated={onUnauthenticated} />
    </MemoryRouter>,
  )
  return onUnauthenticated
}

function fillAndLook(lat = '50.1109', lng = '8.6821', radius = '2') {
  fireEvent.change(screen.getByLabelText('Latitude'), { target: { value: lat } })
  fireEvent.change(screen.getByLabelText('Longitude'), { target: { value: lng } })
  fireEvent.change(screen.getByLabelText('Radius (km)'), { target: { value: radius } })
  fireEvent.click(screen.getByRole('button', { name: 'Look around' }))
}

beforeEach(() => {
  window.sessionStorage.clear()
})
afterEach(() => {
  vi.unstubAllGlobals()
  window.sessionStorage.clear()
})

describe('before a run', () => {
  it('points to Home when there is no finished plan, and calls nothing', () => {
    const { calls } = api({})
    renderPage()
    expect(screen.getByRole('heading', { name: 'Start from your plan' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to Home' })).toHaveAttribute('href', '/home')
    expect(calls).toHaveLength(0)
  })

  it('refuses bad coordinates on the page without calling the server', () => {
    saveRunId(R1_RUN_ID)
    const { calls } = api({})
    renderPage()
    fillAndLook('120', '8.6')
    expect(screen.getByRole('alert')).toHaveTextContent(/Latitude must be between -90 and 90/)
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  })
})

describe('starting a run', () => {
  it('sends the contract body, waits, then shows the places the server found', async () => {
    saveRunId(R1_RUN_ID)
    const { calls } = api({
      'POST /': () => ok(R2_BODY.running, 202),
      [`GET /${R2_RUN_ID}`]: () => ok(R2_BODY.finished),
    })
    renderPage()
    fillAndLook()

    expect(await screen.findByLabelText('Looking around the apartment')).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
      r1_run_id: R1_RUN_ID,
      origin: { latitude: 50.1109, longitude: 8.6821 },
      radius_km: 2,
    })

    const rail = await screen.findByRole('navigation', { name: 'Categories' }, SLOW)
    expect(within(rail).getByText('Transit station')).toBeInTheDocument()
    expect(within(rail).getByText('2 places')).toBeInTheDocument()
    expect(screen.getByText('Search finished')).toBeInTheDocument()
    expect(screen.getByText('Hauptbahnhof')).toBeInTheDocument()
  })

  it('shows the reason the server gave for a 422 and keeps what was typed', async () => {
    saveRunId(R1_RUN_ID)
    api({ 'POST /': () => ok(R2_ERROR.rejected, 422) })
    renderPage()
    fillAndLook('50.1', '8.6', '3')
    expect(await screen.findByText('radius_km must be greater than 0')).toBeInTheDocument()
    expect(screen.getByLabelText('Radius (km)')).toHaveValue('3')
    expect(screen.getByRole('button', { name: 'Look around' })).toBeEnabled()
  })

  it.each([
    ['503 store down', ok(R2_ERROR.storeDown, 503)],
    ['network error', 'network-error' as const],
  ])('says nothing was lost after a %s and keeps the form', async (_name, reply) => {
    saveRunId(R1_RUN_ID)
    api({ 'POST /': () => reply })
    renderPage()
    fillAndLook('50.1', '8.6', '2')
    expect(await screen.findByText("We couldn't reach the search service")).toBeInTheDocument()
    expect(screen.getByLabelText('Latitude')).toHaveValue('50.1')
  })

  it('tells the renter the plan is gone when start answers 404', async () => {
    saveRunId(R1_RUN_ID)
    api({ 'POST /': () => ok(R2_ERROR.r1NotFound, 404) })
    renderPage()
    fillAndLook()
    expect(await screen.findByText("This search can't be found")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start a new search' })).toBeInTheDocument()
  })

  it('locks the button while the start call is in flight (no double start)', async () => {
    saveRunId(R1_RUN_ID)
    let release: (r: Reply) => void = () => {}
    const { calls } = api({ 'POST /': () => new Promise<Reply>((r) => (release = r)) })
    renderPage()
    fillAndLook()
    const button = await screen.findByRole('button', { name: 'Starting…' })
    expect(button).toBeDisabled()
    fireEvent.click(button)
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(1)
    release(ok(R2_BODY.running, 202))
  })
})

describe('a refresh', () => {
  it('restores a finished run from the status endpoint without starting another', async () => {
    saveR2Run(SAVED)
    const { calls } = api({ [`GET /${R2_RUN_ID}`]: () => ok(R2_BODY.finished) })
    renderPage(`/proximity_info?run=${R2_RUN_ID}`)
    expect(await screen.findByRole('navigation', { name: 'Categories' })).toBeInTheDocument()
    expect(screen.getByText(/Within 2 km of 50.1109, 8.6821/)).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })

  it('opens a run named only in the URL, without its coordinates', async () => {
    api({ [`GET /${R2_RUN_ID}`]: () => ok(R2_BODY.finished) })
    renderPage(`/proximity_info?run=${R2_RUN_ID}`)
    expect(await screen.findByText('Hauptbahnhof')).toBeInTheDocument()
    expect(screen.getByText(/Places near the apartment/)).toBeInTheDocument()
  })

  it('resets to the start screen when the run no longer exists (404)', async () => {
    saveR2Run(SAVED)
    api({ [`GET /${R2_RUN_ID}`]: () => ok(R2_ERROR.notFound, 404) })
    renderPage(`/proximity_info?run=${R2_RUN_ID}`)
    expect(await screen.findByText("This search can't be found")).toBeInTheDocument()
    expect(window.sessionStorage.getItem('homescout.r2.run')).toBeNull()
  })

  it('hands an expired session to the app (401)', async () => {
    saveR2Run(SAVED)
    api({ [`GET /${R2_RUN_ID}`]: () => ok({ error: 'Unauthorized' }, 401) })
    const onUnauthenticated = renderPage(`/proximity_info?run=${R2_RUN_ID}`)
    await waitFor(() => expect(onUnauthenticated).toHaveBeenCalled())
  })
})

describe('what a finished run can contain', () => {
  it('keeps every planned category in the rail, marking the ones with nothing found', async () => {
    saveR2Run(SAVED)
    api({ [`GET /${R2_RUN_ID}`]: () => ok(R2_BODY.finishedEmpty) })
    renderPage(`/proximity_info?run=${R2_RUN_ID}`)
    const rail = await screen.findByRole('navigation', { name: 'Categories' })
    expect(within(rail).getAllByText('None found').length).toBeGreaterThan(0)
  })

  it('shows a place with only the fields Google always returns', async () => {
    saveR2Run(SAVED)
    api({ [`GET /${R2_RUN_ID}`]: () => ok(R2_BODY.finishedSparse) })
    renderPage(`/proximity_info?run=${R2_RUN_ID}`)
    expect(await screen.findByText('Unnamed place')).toBeInTheDocument()
  })

  it('still lists the categories R2 returned when the plan cannot be read', async () => {
    saveR2Run(SAVED)
    mockR2Api(
      () => ok(R2_BODY.finished),
      () => ok({ error: 'Run not found' }, 404),
    )
    renderPage(`/proximity_info?run=${R2_RUN_ID}`)
    const rail = await screen.findByRole('navigation', { name: 'Categories' })
    expect(within(rail).getByText('Supermarket')).toBeInTheDocument()
  })
})

describe('a failed run', () => {
  it('offers Try again when retryable, and calls the retry endpoint once', async () => {
    saveR2Run(SAVED)
    const { calls } = api({
      [`GET /${R2_RUN_ID}`]: () => ok(R2_BODY.failed(true, 'discovery')),
      [`POST /${R2_RUN_ID}/retry`]: () => ok(R2_BODY.runningAfterDiscovery, 202),
    })
    renderPage(`/proximity_info?run=${R2_RUN_ID}`)
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }))
    expect(await screen.findByLabelText('Looking around the apartment')).toBeInTheDocument()
    expect(calls.filter((c) => c.path.endsWith('/retry'))).toHaveLength(1)
  })

  it('offers only a new search when not retryable', async () => {
    saveRunId(R1_RUN_ID)
    saveR2Run(SAVED)
    api({ [`GET /${R2_RUN_ID}`]: () => ok(R2_BODY.failed(false)) })
    renderPage(`/proximity_info?run=${R2_RUN_ID}`)
    expect(await screen.findByText('This search stopped for good')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start a new search' }))
    expect(await screen.findByRole('button', { name: 'Look around' })).toBeInTheDocument()
  })

  it('re-reads the run after a 409 on retry and shows what it is now', async () => {
    saveR2Run(SAVED)
    let reads = 0
    api({
      [`GET /${R2_RUN_ID}`]: () => ok(reads++ === 0 ? R2_BODY.failed(true) : R2_BODY.failed(false)),
      [`POST /${R2_RUN_ID}/retry`]: () => ok(R2_ERROR.conflict('failed', false), 409),
    })
    renderPage(`/proximity_info?run=${R2_RUN_ID}`)
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('This search stopped for good')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })
})
