import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { HomePage } from '@/pages/HomePage'

const TEXTAREA_NAME =
  'Describe your ideal neighborhood and paste the address you want evaluated…'

function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms)
  })
}

function stepStates() {
  return within(screen.getByRole('list', { name: 'Search progress' }))
    .getAllByRole('listitem')
    .map((row) => row.dataset.state?.[0])
    .join('')
}

function submitBrief(text?: string) {
  const textarea = screen.getByRole('textbox', { name: TEXTAREA_NAME })
  if (text !== undefined) {
    fireEvent.change(textarea, { target: { value: text } })
  }
  fireEvent.submit(screen.getByRole('form', { name: 'Neighborhood brief' }))
}

describe('HomePage search run', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('runs intro, five 3s steps, then shows the result and unlocks the composer', () => {
    render(<HomePage message="Welcome King jee!" />)
    submitBrief('Quiet street near a park')

    // 0ms: heading fades, composer locks.
    expect(screen.getByRole('textbox', { name: TEXTAREA_NAME })).toHaveAttribute('readonly')
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    expect(screen.getByRole('combobox', { name: /Model/ })).toHaveAttribute('data-disabled')

    // 200ms: heading leaves the layout; timeline not yet shown.
    advance(200)
    expect(screen.getByRole('heading', { name: 'Start your Homescout', hidden: true })).not.toBeVisible()
    expect(screen.queryByRole('list', { name: 'Search progress' })).not.toBeInTheDocument()

    // 600ms: timeline appears with step 1 active.
    advance(400)
    expect(stepStates()).toBe('apppp')
    expect(screen.getByText('Step 1 of 5: Breaking your needs into higher-level categories')).toBeInTheDocument()

    advance(3000)
    expect(stepStates()).toBe('cappp')
    advance(3000 * 2)
    expect(stepStates()).toBe('cccap')
    expect(screen.getByRole('img', { name: /Map of the area/ })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Result' })).not.toBeInTheDocument()

    advance(3000 * 2)
    expect(stepStates()).toBe('ccccc')
    expect(screen.getByRole('region', { name: 'Result' })).toHaveTextContent('82 / 100')
    expect(screen.getByRole('textbox', { name: TEXTAREA_NAME })).not.toHaveAttribute('readonly')
    expect(screen.getByRole('textbox', { name: TEXTAREA_NAME })).toHaveValue('Quiet street near a park')
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled()
  })

  it('resets to pending and restarts from step 1 on a new search', () => {
    render(<HomePage message="Welcome King jee!" />)
    submitBrief('Quiet street near a park')
    advance(600 + 15000)
    expect(screen.getByRole('region', { name: 'Result' })).toBeInTheDocument()

    submitBrief()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()

    // Result and map fade out, then every step goes back to pending.
    advance(200)
    expect(screen.queryByRole('region', { name: 'Result' })).not.toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /Map of the area/ })).not.toBeInTheDocument()
    expect(stepStates()).toBe('ppppp')

    advance(300)
    expect(stepStates()).toBe('apppp')
    // Heading stays hidden for the rest of the session.
    expect(screen.getByRole('heading', { name: 'Start your Homescout', hidden: true })).not.toBeVisible()
  })
})
