import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { LoginPage } from '@/pages/LoginPage'
import { SignupPage } from '@/pages/SignupPage'
import { getPasswordInput, renderLoginForm } from '@/test/loginTestUtils'

/** jsdom has no matchMedia; the star background reads prefers-reduced-motion. */
function stubMatchMedia() {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )
}

/** A key event whose Caps Lock state is fixed (jsdom ignores modifierCapsLock). */
function keyEvent(type: 'keydown' | 'keyup', capsLock: boolean) {
  const event = new KeyboardEvent(type, { key: 'A', bubbles: true })
  Object.defineProperty(event, 'getModifierState', {
    value: (key: string) => key === 'CapsLock' && capsLock,
  })
  return event
}

describe('Sign-in Olive Glass theme', () => {
  beforeEach(stubMatchMedia)
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('applies the olive theme only while the sign-in page is shown', () => {
    const { unmount } = render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )
    expect(document.documentElement).toHaveClass('theme-olive', 'auth-olive')

    unmount()
    expect(document.documentElement).not.toHaveClass('theme-olive')
    expect(document.documentElement).not.toHaveClass('auth-olive')
  })

  it('applies the same olive theme on the sign-up page, only while it is shown', () => {
    const { unmount } = render(
      <MemoryRouter>
        <SignupPage />
      </MemoryRouter>,
    )
    expect(document.documentElement).toHaveClass('theme-olive', 'auth-olive')

    unmount()
    expect(document.documentElement).not.toHaveClass('auth-olive')
  })

  it('shows the features as an agent workflow, each card with its accent', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )
    const workflow = screen.getByRole('list', { name: 'How the Homescout agent works' })
    const accents = within(workflow)
      .getAllByRole('listitem')
      .filter((item) => item.tagName === 'ARTICLE')
      .map((card) => card.style.getPropertyValue('--accent'))

    expect(accents).toEqual(['#9A6B00', '#1D6FA3', '#1F7A80', '#B0306E', '#B35A12', '#B3302F'])
    expect(screen.queryByRole('button', { name: /see results/i })).toBeNull()
  })

  it('shows the sign-in heading and a menu bar with the five sections', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Tell us your perfect apartment and neighborhood. Our agent finds the match.',
    )
    expect(
      screen.getByText('Describe the life you want. Homescout searches, compares, inquires and keeps you updated.'),
    ).toBeTruthy()
    const heading = screen.getByRole('heading', { level: 1 })
    expect(Array.from(heading.querySelectorAll('em')).map((em) => em.textContent)).toEqual([
      'apartment',
      'neighborhood',
    ])
    expect(heading.querySelectorAll('[aria-hidden="true"]')).toHaveLength(2)

    const menu = screen.getByRole('navigation', { name: 'Main' })
    expect(within(menu).getAllByRole('link').map((link) => link.textContent)).toEqual([
      'Home',
      'Product',
      'Price',
      'Reviews',
      'About us',
    ])
  })

  it('gives the sign-up page the sign-in heading, menu, workflow and an olive form card', () => {
    render(
      <MemoryRouter>
        <SignupPage />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Tell us your perfect apartment and neighborhood. Our agent finds the match.',
    )
    const menu = screen.getByRole('navigation', { name: 'Main' })
    expect(within(menu).getAllByRole('link').map((link) => link.textContent)).toEqual([
      'Home',
      'Product',
      'Price',
      'Reviews',
      'About us',
    ])
    expect(screen.getByRole('list', { name: 'How the Homescout agent works' })).toBeTruthy()
    expect(document.querySelectorAll('[data-slot="feature-card-root"]')).toHaveLength(0)
    expect(document.querySelector('[data-slot="auth-card"]')).toBeTruthy()
    expect(document.querySelector('[data-slot="auth-submit"]')).toBeTruthy()
    expect(screen.getByText('Create your account')).toBeTruthy()
  })
})

describe('Caps Lock hint', () => {
  it('warns while Caps Lock is on in the password field, and clears when it goes off', () => {
    renderLoginForm()
    const password = getPasswordInput()

    fireEvent(password, keyEvent('keydown', false))
    expect(screen.queryByText('Caps Lock is on')).toBeNull()

    fireEvent(password, keyEvent('keydown', true))
    expect(screen.getByRole('status')).toHaveTextContent('Caps Lock is on')
    expect(password).toHaveAttribute('aria-describedby', 'caps-lock-hint')

    fireEvent(password, keyEvent('keyup', false))
    expect(screen.queryByText('Caps Lock is on')).toBeNull()
    expect(password).not.toHaveAttribute('aria-describedby')
  })
})
