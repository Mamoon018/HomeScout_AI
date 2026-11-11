import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { NeighborhoodBriefComposer } from '@/features/composer/components/neighborhood-brief-composer'

const TEXTAREA_NAME =
  'Describe your ideal neighborhood and paste the address you want evaluated…'

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

  it('keeps Send disabled until there is text, and hides the placeholder once typing starts', async () => {
    const user = userEvent.setup()
    render(<NeighborhoodBriefComposer />)
    const send = screen.getByRole('button', { name: 'Send' })
    const textarea = screen.getByRole('textbox', { name: TEXTAREA_NAME })
    const placeholder = () => textarea.parentElement?.querySelector(':scope > div[aria-hidden="true"]')

    expect(send).toBeDisabled()
    expect(placeholder()).toHaveTextContent('Describe your ideal neighborhood')

    await user.type(textarea, 'Quiet street')

    expect(send).toBeEnabled()
    expect(placeholder()).toBeNull()
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

  it('submits on Ctrl+Enter but not on plain Enter', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<NeighborhoodBriefComposer onSubmit={onSubmit} />)
    const textarea = screen.getByRole('textbox', { name: TEXTAREA_NAME })

    await user.type(textarea, '  Walkable to a park{Enter}')
    expect(onSubmit).not.toHaveBeenCalled()

    await user.keyboard('{Control>}{Enter}{/Control}')
    expect(onSubmit).toHaveBeenCalledWith({
      brief: 'Walkable to a park',
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
