import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { login } from '@/features/auth/api/authApi'
import { LOGIN_USER_MESSAGES } from '@/features/auth/utils/loginErrors'
import { INVALID_INPUT_MESSAGE } from '@/features/auth/utils/loginSchema'
import {
  fillValidLoginForm,
  findToastMessage,
  getPasswordInput,
  getSubmitButton,
  renderLoginForm,
} from '@/test/loginTestUtils'

const mockNavigate = vi.fn()

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
    await fillValidLoginForm(user)
    await user.click(getSubmitButton())

    expect(
      screen.getByRole('button', { name: 'Signing in...' }),
    ).toBeDisabled()

    resolveLogin({ ok: true, status: 200, data: { message: 'Login successful' } })
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/auth/callback', {
        state: { cookie: null },
      })
    })
  })

  it('navigates to callback on success', async () => {
    const user = userEvent.setup()
    const cookie = {
      sent: true,
      name: 'access_token',
      http_only: true,
      secure: true,
      same_site: 'Strict',
      path: '/',
    }
    mockedLogin.mockResolvedValue({
      ok: true,
      status: 200,
      data: { message: 'Login successful', cookie },
    })

    renderLoginForm()
    await fillValidLoginForm(user)
    await user.click(getSubmitButton())

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/auth/callback', {
        state: { cookie },
      })
    })
  })

  it('shows generic error on 401', async () => {
    const user = userEvent.setup()
    mockedLogin.mockResolvedValue({
      ok: false,
      status: 401,
      data: { error: 'Invalid email or password' },
    })

    renderLoginForm()
    await fillValidLoginForm(user)
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
    await fillValidLoginForm(user)
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
    await fillValidLoginForm(user)
    await user.click(getSubmitButton())

    await findToastMessage(LOGIN_USER_MESSAGES.connection)
  })
})
