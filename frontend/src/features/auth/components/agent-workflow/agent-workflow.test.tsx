import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { AgentWorkflow } from './agent-workflow'
import { ALL_DONE_PHASE, cardState, isNodeLit, travelingWire, wireState } from './use-agent-loop'

const ORDER = [
  'Home Wishlist',
  'Deep Search',
  'Analysis Report',
  'Matching Engine',
  'Owners Outreach',
  'User Feedback',
]

function stubMatchMedia(reducedMotion: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches: reducedMotion && query.includes('prefers-reduced-motion'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )
}

/** The workflow cards (articles), not the list rows inside Matching Engine. */
function workflowCards() {
  return screen.getAllByRole('listitem').filter((item) => item.tagName === 'ARTICLE')
}

function cardStates() {
  return workflowCards().map((card) => card.getAttribute('data-state'))
}

describe('agent loop state', () => {
  it('runs cards in order with a travel phase before each one', () => {
    expect(travelingWire(0)).toBe(0)
    expect(cardState(1, 0)).toBe('running')
    expect(cardState(2, 0)).toBe('done')
    expect(travelingWire(2)).toBe(1)
    expect(cardState(2, 1)).toBe('queued')
    expect(cardState(11, 5)).toBe('running')
    expect(travelingWire(11)).toBeNull()
  })

  it('marks every card done and every wire traveled at the end, with the agent lit', () => {
    expect(ORDER.map((_, card) => cardState(ALL_DONE_PHASE, card))).toEqual(Array(6).fill('done'))
    expect([0, 1, 2, 3, 4, 5].map((wire) => wireState(ALL_DONE_PHASE, wire))).toEqual(Array(6).fill('traveled'))
    expect(isNodeLit(0)).toBe(true)
    expect(isNodeLit(ALL_DONE_PHASE)).toBe(true)
    expect(isNodeLit(3)).toBe(false)
  })

  it('carries the light only on the current wire', () => {
    expect([0, 1, 2].map((wire) => wireState(2, wire))).toEqual(['traveled', 'carrying', 'ahead'])
  })
})

describe('AgentWorkflow', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('lists the six features in workflow order, each with its title as a heading', () => {
    stubMatchMedia(false)
    render(<AgentWorkflow />)

    expect(screen.getByRole('list', { name: 'How the Homescout agent works' })).toBeTruthy()
    const cards = workflowCards()
    expect(cards.map((card) => within(card).getByRole('heading').textContent)).toEqual(ORDER)
  })

  it('advances the run over time and pauses from the agent button', () => {
    vi.useFakeTimers()
    stubMatchMedia(false)
    render(<AgentWorkflow />)

    expect(cardStates()).toEqual(Array(6).fill('queued'))

    act(() => vi.advanceTimersByTime(500))
    expect(cardStates()[0]).toBe('running')

    fireEvent.click(screen.getByRole('button', { name: 'Pause the Homescout agent demo' }))
    act(() => vi.advanceTimersByTime(10_000))
    expect(cardStates()[0]).toBe('running')

    fireEvent.click(screen.getByRole('button', { name: 'Play the Homescout agent demo' }))
    // One act per phase: React schedules the next phase's timer after each update.
    act(() => vi.advanceTimersByTime(1800))
    act(() => vi.advanceTimersByTime(1100))
    expect(cardStates().slice(0, 2)).toEqual(['done', 'running'])
  })

  it('shows a still snapshot when motion is reduced, until the visitor presses play', () => {
    vi.useFakeTimers()
    stubMatchMedia(true)
    render(<AgentWorkflow />)

    const snapshot = ['done', 'done', 'running', 'queued', 'queued', 'queued']
    expect(cardStates()).toEqual(snapshot)
    act(() => vi.advanceTimersByTime(20_000))
    expect(cardStates()).toEqual(snapshot)
    expect(screen.getByRole('button', { name: 'Play the Homescout agent demo' })).toBeTruthy()
  })

  it('keeps the card content readable: Matching Engine is an ordered list and Deep Search stats a description list', () => {
    stubMatchMedia(false)
    const { container } = render(<AgentWorkflow />)

    expect(container.querySelectorAll('ol li')).toHaveLength(4)
    expect(Array.from(container.querySelectorAll('dt')).map((term) => term.textContent)).toEqual([
      'Radius',
      'Budget',
      'Listings',
    ])
    expect(screen.getByText('Is a parking spot included?')).toBeTruthy()
  })
})
