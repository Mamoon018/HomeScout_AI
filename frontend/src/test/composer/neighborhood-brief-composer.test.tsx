import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { NeighborhoodBriefComposer } from '@/features/composer/components/neighborhood-brief-composer'

const TEXTAREA_NAME =
  'Describe your ideal neighborhood and paste the address you want evaluated…'
/** Long enough for the composer to accept: the backend wants at least 100 words. */
const LONG_BRIEF = Array.from({ length: 100 }, (_, i) => `word${i}`).join(' ')

describe('NeighborhoodBriefComposer', () => {
  it('renders every toolbar, input and footer element', () => {
    render(<NeighborhoodBriefComposer />)

    expect(screen.getByRole('form', { name: 'Neighborhood brief' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Model: Homescout 1.0' })).toHaveAttribute(
      'aria-haspopup',
      'listbox',
    )
    expect(screen.getByRole('button', { name: 'Search' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('combobox', { name: 'Reasoning: Deep' })).toBeInTheDocument()
    expect(screen.getByText('Search up to 2 km radius')).toBeInTheDocument()
    expect(screen.getAllByRole('separator')).toHaveLength(2)
    expect(screen.getByRole('textbox', { name: TEXTAREA_NAME })).toBeInTheDocument()
    expect(screen.queryByText('Press')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toHaveAttribute('type', 'submit')
  })

  it('keeps Send disabled until the brief has 100 words, and hides the placeholder once typing starts', async () => {
    const user = userEvent.setup()
    render(<NeighborhoodBriefComposer />)
    const send = screen.getByRole('button', { name: 'Send' })
    const textarea = screen.getByRole('textbox', { name: TEXTAREA_NAME })
    const placeholder = () => textarea.parentElement?.querySelector(':scope > div[aria-hidden="true"]')

    expect(send).toBeDisabled()
    expect(placeholder()).toHaveTextContent('Describe your ideal neighborhood')

    await user.type(textarea, 'Quiet street')

    expect(send).toBeDisabled()
    expect(screen.getByText(/2 of 100 words/)).toBeInTheDocument()
    expect(placeholder()).toBeNull()

    await user.clear(textarea)
    await user.click(textarea)
    await user.paste(LONG_BRIEF)

    expect(send).toBeEnabled()
    expect(screen.getByText('100 words')).toBeInTheDocument()
  })

  it('toggles search on and off', async () => {
    const user = userEvent.setup()
    render(<NeighborhoodBriefComposer />)
    const search = screen.getByRole('button', { name: 'Search' })

    await user.click(search)
    expect(search).toHaveAttribute('aria-pressed', 'true')

    await user.click(search)
    expect(search).toHaveAttribute('aria-pressed', 'false')
  })

  it('shows the reason for a refused brief under the card until the renter edits', async () => {
    const user = userEvent.setup()
    const onEdit = vi.fn()
    render(<NeighborhoodBriefComposer error="Please write yours in English." onEdit={onEdit} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Please write yours in English.')
    await user.type(screen.getByRole('textbox', { name: TEXTAREA_NAME }), 'a')
    expect(onEdit).toHaveBeenCalled()
  })

  it('submits on Ctrl+Enter but not on plain Enter, and not before 100 words', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<NeighborhoodBriefComposer onSubmit={onSubmit} />)
    const textarea = screen.getByRole('textbox', { name: TEXTAREA_NAME })

    await user.type(textarea, 'Walkable to a park{Enter}')
    await user.keyboard('{Control>}{Enter}{/Control}')
    expect(onSubmit).not.toHaveBeenCalled()

    await user.clear(textarea)
    await user.click(textarea)
    await user.paste(`  ${LONG_BRIEF}`)
    await user.keyboard('{Enter}')
    expect(onSubmit).not.toHaveBeenCalled()

    await user.keyboard('{Control>}{Enter}{/Control}')
    expect(onSubmit).toHaveBeenCalledWith({
      brief: LONG_BRIEF,
      model: 'Homescout 1.0',
      reasoning: 'Deep',
      searchEnabled: false,
    })
  })

  it('shows a Stop button while submitting', async () => {
    const user = userEvent.setup()
    const onStop = vi.fn()
    render(<NeighborhoodBriefComposer isSubmitting onStop={onStop} />)

    await user.click(screen.getByRole('button', { name: 'Stop' }))
    expect(onStop).toHaveBeenCalledOnce()
  })
})
