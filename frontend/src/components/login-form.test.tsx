import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { login } from '@/features/auth/api/authApi'
import { LOGIN_USER_MESSAGES } from '@/features/auth/utils/loginErrors'
import { INVALID_INPUT_MESSAGE } from '@/features/auth/utils/loginSchema'
import { MockTurnstile } from '@/test/mocks/turnstile'
import {
  completeLoginCaptcha,
  fillValidLoginForm,
  fillValidLoginFormWithCaptcha,
  findToastMessage,
  getPasswordInput,
  getSubmitButton,
  renderLoginForm,
} from '@/test/loginTestUtils'

const mockNavigate = vi.fn()

vi.mock('@marsidev/react-turnstile', () => ({
  Turnstile: MockTurnstile,
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  )
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

vi.mock('@/features/auth/api/authApi', async () => {
  const actual = await vi.importActual<typeof import('@/features/auth/api/authApi')>(
    '@/features/auth/api/authApi',
  )
  return {
    ...actual,
    login: vi.fn(),
  }
})

const mockedLogin = vi.mocked(login)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('LoginForm', () => {
  it('shows Invalid Input for empty submit', async () => {
    const user = userEvent.setup()
    renderLoginForm()

    await completeLoginCaptcha(user)
    await user.click(getSubmitButton())

    expect(await screen.findAllByText(INVALID_INPUT_MESSAGE)).toHaveLength(2)
    expect(mockedLogin).not.toHaveBeenCalled()
  })

  it('toggles password visibility with checkbox', async () => {
    const user = userEvent.setup()
    renderLoginForm()

    expect(getPasswordInput()).toHaveAttribute('type', 'password')

    await user.click(screen.getByRole('checkbox', { name: 'Show password' }))
    expect(getPasswordInput()).toHaveAttribute('type', 'text')

    await user.click(screen.getByRole('checkbox', { name: 'Show password' }))
    expect(getPasswordInput()).toHaveAttribute('type', 'password')
  })

  it('disables submit while loading', async () => {
    const user = userEvent.setup()
    let resolveLogin!: (value: Awaited<ReturnType<typeof login>>) => void
    const loginPromise = new Promise<Awaited<ReturnType<typeof login>>>((resolve) => {
      resolveLogin = resolve
    })
    mockedLogin.mockReturnValue(loginPromise)

    renderLoginForm()
    await fillValidLoginFormWithCaptcha(user)
    await user.click(getSubmitButton())

    expect(
      screen.getByRole('button', { name: 'Signing in...' }),
    ).toBeDisabled()

    resolveLogin({
      ok: true,
      status: 200,
      data: { message: 'Login successful', user_id: 'user-1', user_name: 'Demo User' },
    })
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/home', { replace: true })
    })
  })

  it('navigates to home on success', async () => {
    const user = userEvent.setup()
    mockedLogin.mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        message: 'Login successful',
        user_id: 'user-1',
        user_name: 'Demo User',
      },
    })

    renderLoginForm()
    await fillValidLoginFormWithCaptcha(user)
    await user.click(getSubmitButton())

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/home', { replace: true })
    })
    expect(localStorage.getItem('homescout.auth.user')).toContain('Demo User')
  })

  it('keeps submit disabled until captcha is completed', async () => {
    const user = userEvent.setup()
    renderLoginForm()

    await fillValidLoginForm(user)
    expect(getSubmitButton()).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Verify captcha' }))
    await user.click(
      screen.getByRole('button', { name: 'Complete captcha challenge' }),
    )
    expect(getSubmitButton()).not.toBeDisabled()
  })

  it('shows generic error on 401', async () => {
    const user = userEvent.setup()
    mockedLogin.mockResolvedValue({
      ok: false,
      status: 401,
      data: { error: 'Invalid email or password' },
    })

    renderLoginForm()
    await fillValidLoginFormWithCaptcha(user)
    await user.click(getSubmitButton())

    await findToastMessage(LOGIN_USER_MESSAGES.invalidCredentials)
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('shows backend message on 429', async () => {
    const user = userEvent.setup()
    const rateLimitMessage =
      'Too many login attempts. Please try again later.'
    mockedLogin.mockResolvedValue({
      ok: false,
      status: 429,
      data: { error: rateLimitMessage },
    })

    renderLoginForm()
    await fillValidLoginFormWithCaptcha(user)
    await user.click(getSubmitButton())

    await findToastMessage(rateLimitMessage)
  })

  it('shows connection error on timeout', async () => {
    const user = userEvent.setup()
    mockedLogin.mockResolvedValue({
      ok: false,
      status: 0,
      data: null,
      aborted: true,
    })

    renderLoginForm()
    await fillValidLoginFormWithCaptcha(user)
    await user.click(getSubmitButton())

    await findToastMessage(LOGIN_USER_MESSAGES.connection)
  })
})
