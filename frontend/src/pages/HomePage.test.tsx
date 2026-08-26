import { render, screen } from '@testing-library/react'
import { HomePage } from '@/pages/HomePage'

describe('HomePage', () => {
  it('shows the welcome message returned by the API', () => {
    render(<HomePage message="Welcome Demo User!" />)

    expect(
      screen.getByRole('heading', { name: 'Welcome Demo User!' }),
    ).toBeInTheDocument()
    expect(screen.getByText('You are signed in.')).toBeInTheDocument()
  })

  it('does not show a greeting while the welcome request has no message', () => {
    render(<HomePage message={null} />)

    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
    expect(screen.queryByText('You are signed in.')).not.toBeInTheDocument()
  })
})
