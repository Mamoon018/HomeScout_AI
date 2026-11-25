import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { HomePage } from '@/pages/HomePage'

/** What the welcome API answered; each test sets it before rendering. */
const welcome = vi.hoisted(() => ({ message: null as string | null }))
vi.mock('@/features/auth/hooks/useWelcomeMessage', () => ({ useWelcomeMessage: () => welcome.message }))
vi.mock('@/features/auth/hooks/useUnauthenticatedRedirect', () => ({ useUnauthenticatedRedirect: () => vi.fn() }))

/** Home reads `?run=`, so it renders inside a router. */
function renderHome(url = '/home') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <HomePage />
    </MemoryRouter>,
  )
}

describe('HomePage', () => {
  it('shows the fixed welcome heading once the welcome API confirms the session', () => {
    welcome.message = 'Welcome Demo User!'
    renderHome()

    expect(
      screen.getByRole('heading', { level: 1, name: 'Start your Homescout' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('Welcome Demo User!')).not.toBeInTheDocument()
    expect(screen.queryByText('You are signed in.')).not.toBeInTheDocument()
  })

  it('applies the Olive Glass theme only while the Home page is shown', () => {
    welcome.message = 'Welcome Demo User!'
    const { unmount } = renderHome()
    expect(document.documentElement).toHaveClass('theme-olive')

    unmount()
    expect(document.documentElement).not.toHaveClass('theme-olive')
  })

  it('does not show a greeting while the welcome request has no message', () => {
    welcome.message = null
    renderHome()

    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
    expect(screen.queryByText('You are signed in.')).not.toBeInTheDocument()
  })
})
