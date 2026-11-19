import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { login } from '@/features/auth/api/authApi'
import { LOGIN_USER_MESSAGES } from '@/features/auth/utils/loginErrors'
import { INVALID_INPUT_MESSAGE } from '@/features/auth/utils/loginSchema'
import {
  completeLoginCaptcha,
  fillValidLoginForm,
  fillValidLoginFormWithCaptcha,
  findToastMessage,
  getPasswordInput,
  getSubmitButton,
  renderLoginForm,
} from '@/test/loginTestUtils'

const { isCaptchaEnabledMock } = vi.hoisted(() => ({
  isCaptchaEnabledMock: vi.fn(() => true),
}))

vi.mock('@/features/auth/utils/captchaConfig', () => ({
  isCaptchaEnabled: () => isCaptchaEnabledMock(),
  getCaptchaSiteKey: () => 'test-site-key',
}))

vi.mock('@marsidev/react-turnstile', async () => {
  const { MockTurnstile } = await import('@/test/mocks/turnstile')
  return { Turnstile: MockTurnstile }
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
  isCaptchaEnabledMock.mockReturnValue(true)
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

    const { path } = renderLoginForm()
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
      expect(path.current).toBe('/home')
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

    const { path } = renderLoginForm()
    await fillValidLoginFormWithCaptcha(user)
    await user.click(getSubmitButton())

    await waitFor(() => {
      expect(path.current).toBe('/home')
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
      await screen.findByRole('button', { name: 'Complete captcha challenge' }),
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

    const { path } = renderLoginForm()
    await fillValidLoginFormWithCaptcha(user)
    await user.click(getSubmitButton())

    await findToastMessage(LOGIN_USER_MESSAGES.invalidCredentials)
    expect(path.current).toBe('/')
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

  it('allows submit without captcha when captcha is disabled in dev', async () => {
    isCaptchaEnabledMock.mockReturnValue(false)
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

    const { path } = renderLoginForm()
    await fillValidLoginForm(user)
    expect(getSubmitButton()).not.toBeDisabled()
    await user.click(getSubmitButton())

    await waitFor(() => {
      expect(path.current).toBe('/home')
    })
    expect(screen.queryByRole('button', { name: 'Verify captcha' })).not.toBeInTheDocument()
  })
})
