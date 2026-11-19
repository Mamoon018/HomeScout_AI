import { render, screen } from '@testing-library/react'
import { HomePage } from '@/pages/HomePage'

describe('HomePage', () => {
  it('shows the fixed welcome heading once the welcome API confirms the session', () => {
    render(<HomePage message="Welcome Demo User!" />)

    expect(
      screen.getByRole('heading', { level: 1, name: 'Start your Homescout' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('Welcome Demo User!')).not.toBeInTheDocument()
    expect(screen.queryByText('You are signed in.')).not.toBeInTheDocument()
  })

  it('applies the Olive Glass theme only while the Home page is shown', () => {
    const { unmount } = render(<HomePage message="Welcome Demo User!" />)
    expect(document.documentElement).toHaveClass('theme-olive')

    unmount()
    expect(document.documentElement).not.toHaveClass('theme-olive')
  })

  it('does not show a greeting while the welcome request has no message', () => {
    render(<HomePage message={null} />)

    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
    expect(screen.queryByText('You are signed in.')).not.toBeInTheDocument()
  })
})
