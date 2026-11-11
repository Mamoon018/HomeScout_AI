import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { HomePage } from '@/pages/HomePage'

const TEXTAREA_NAME =
  'Describe your ideal neighborhood and paste the address you want evaluated…'

function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms)
  })
}

function submitBrief(text?: string) {
  const textarea = screen.getByRole('textbox', { name: TEXTAREA_NAME })
  if (text !== undefined) {
    fireEvent.change(textarea, { target: { value: text } })
  }
  fireEvent.submit(screen.getByRole('form', { name: 'Neighborhood brief' }))
}

const PLAN_HEADING = { name: "What I'll look for" }

describe('HomePage R1 run', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('reads the brief, plans, shows the result, then unlocks the composer', () => {
    render(<HomePage message="Welcome King jee!" clarificationQuestions={[]} />)
    submitBrief('Quiet street near a park')

    // 0ms: heading fades, composer locks.
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    expect(screen.queryByRole('heading', { name: 'Instructions decoded' })).not.toBeInTheDocument()

    // 600ms: the breakdown opens with all three readings together.
    advance(600)
    expect(screen.getByRole('heading', { name: 'Instructions decoded' })).toBeInTheDocument()
    for (const name of ['User Persona', 'What you asked for', 'Not sure yet']) {
      expect(screen.getByRole('region', { name })).toBeInTheDocument()
    }
    expect(screen.getByText('relocating to Munich in February')).toBeInTheDocument()
    expect(screen.queryByRole('heading', PLAN_HEADING)).not.toBeInTheDocument()

    // Extraction ends, planning starts.
    advance(2800)
    expect(screen.getByRole('heading', PLAN_HEADING)).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Categories' })).not.toBeInTheDocument()

    // Plan lands: categories with their deep checks, composer unlocked.
    advance(2400)
    const categories = screen.getByRole('list', { name: 'Categories' })
    expect(within(categories).getByText('Transit station')).toBeInTheDocument()
    expect(within(categories).getByText('Rail service type')).toBeInTheDocument()
        expect(screen.getByRole('textbox', { name: TEXTAREA_NAME })).toHaveValue('Quiet street near a park')
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled()
  })

  it('folds the breakdown away once the plan lands, and can reopen it', () => {
    render(<HomePage message="Welcome King jee!" clarificationQuestions={[]} />)
    submitBrief('Quiet street near a park')
    advance(600 + 2800 + 2400)

    expect(screen.getByRole('button', { name: 'Hide breakdown' })).toHaveAttribute('aria-expanded', 'true')
    advance(1200)
    const toggle = screen.getByRole('button', { name: 'Show breakdown' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText(/8 things about you/)).toBeInTheDocument()

    fireEvent.click(toggle)
    expect(screen.getByRole('button', { name: 'Hide breakdown' })).toBeInTheDocument()
  })

  it('restarts from the breakdown on a new search', () => {
    render(<HomePage message="Welcome King jee!" clarificationQuestions={[]} />)
    submitBrief('Quiet street near a park')
    advance(600 + 2800 + 2400)
    expect(screen.getByRole('list', { name: 'Categories' })).toBeInTheDocument()

    submitBrief()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()

    advance(200)
    expect(screen.queryByRole('heading', { name: 'Instructions decoded' })).not.toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Categories' })).not.toBeInTheDocument()

    advance(300)
    expect(screen.getByRole('heading', { name: 'Instructions decoded' })).toBeInTheDocument()
    // Heading stays hidden for the rest of the session.
    expect(screen.getByRole('heading', { name: 'Start your Homescout', hidden: true })).not.toBeVisible()
  })

  it('pauses for the question, shows the answer in the breakdown, then plans', async () => {
    render(<HomePage message="Welcome King jee!" />)
    submitBrief('Quiet street near a park')
    advance(600 + 2800)

    // The question hangs off "Not sure yet"; nothing moves while the renter answers.
    expect(screen.getByRole('form', { name: 'Clarification questions' })).toBeInTheDocument()
    expect(screen.getByText('Needs one answer from you')).toBeInTheDocument()
    advance(10000)
    expect(screen.queryByRole('heading', PLAN_HEADING)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('radio', { name: 'a private balcony or loggia' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }))
    await act(async () => {})

    // The category now carries what the renter meant, and the plan starts.
    expect(
      within(screen.getByRole('region', { name: 'What you asked for' })).getByText('a private balcony or loggia'),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', PLAN_HEADING)).toBeInTheDocument()

    advance(2400)
    expect(screen.getByRole('list', { name: 'Categories' })).toBeInTheDocument()
  })
})
