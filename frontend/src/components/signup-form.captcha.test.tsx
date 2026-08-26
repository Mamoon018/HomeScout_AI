import { AuthApiError } from '@supabase/supabase-js'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { signUp } from '@/features/auth/api/authApi'
import {
  SIGNUP_USER_MESSAGES,
} from '@/features/auth/utils/signupErrors'
import { MockTurnstile } from '@/test/mocks/turnstile'
import {
  completeCaptcha,
  expectCaptchaNonInteractive,
  expectCaptchaNotVerified,
  expectSubmitDisabled,
  expectSubmitEnabled,
  fillSignupFormWithPasswordMismatch,
  fillValidSignupForm,
  findToastMessage,
  getSubmitButton,
  openCaptchaWidget,
  renderSignupForm,
} from '@/test/signupTestUtils'

vi.mock('@/features/auth/utils/captchaConfig', () => ({
  isCaptchaEnabled: () => true,
  getCaptchaSiteKey: () => 'test-site-key',
}))

vi.mock('@marsidev/react-turnstile', () => ({
  Turnstile: MockTurnstile,
}))

vi.mock('@/features/auth/api/authApi', () => ({
  signUp: vi.fn(),
}))

const mockedSignUp = vi.mocked(signUp)

const SUCCESS_MESSAGE = 'Successfully created an account for you!'

function createDeferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SignupForm captcha UX', () => {
  describe('Initialization (3)', () => {
    it('on load, captcha is not verified', async () => {
      renderSignupForm()
      await expectCaptchaNotVerified()
    })
  })

  describe('Transition (1)', () => {
    it('submit stays disabled with valid form but no captcha', async () => {
      const user = userEvent.setup()
      renderSignupForm()

      await fillValidSignupForm(user)
      expectSubmitDisabled()
      expect(mockedSignUp).not.toHaveBeenCalled()
    })

    it('opening captcha shows widget, submit still disabled', async () => {
      const user = userEvent.setup()
      renderSignupForm()

      await openCaptchaWidget(user)

      expect(
        screen.getByRole('button', { name: 'Complete captcha challenge' }),
      ).toBeInTheDocument()
      expectSubmitDisabled()
    })

    it('completing captcha enables submit', async () => {
      const user = userEvent.setup()
      renderSignupForm()

      await completeCaptcha(user)
      expectSubmitEnabled()
    })

    it('after reset, user must complete captcha again to submit', async () => {
      const user = userEvent.setup()
      mockedSignUp.mockResolvedValue({
        data: { user: { identities: [{ id: 'identity-1' }] } },
        error: null,
      } as Awaited<ReturnType<typeof signUp>>)

      renderSignupForm()
      await fillValidSignupForm(user)
      await completeCaptcha(user)
      await user.click(getSubmitButton())

      await findToastMessage(SUCCESS_MESSAGE)
      await expectCaptchaNotVerified()

      await openCaptchaWidget(user)
      expect(
        screen.getByRole('button', { name: 'Complete captcha challenge' }),
      ).toBeInTheDocument()
      expectSubmitDisabled()

      await user.click(
        screen.getByRole('button', { name: 'Complete captcha challenge' }),
      )
      expectSubmitEnabled()
    })
  })

  describe('Lifecycle/reset (14)', () => {
    it('validation failure resets captcha', async () => {
      const user = userEvent.setup()
      renderSignupForm()

      await fillSignupFormWithPasswordMismatch(user)
      await completeCaptcha(user)
      await user.click(getSubmitButton())

      await findToastMessage(SIGNUP_USER_MESSAGES.validation)
      await expectCaptchaNotVerified()
      expect(mockedSignUp).not.toHaveBeenCalled()
    })

    it('API failure resets captcha', async () => {
      const user = userEvent.setup()
      mockedSignUp.mockResolvedValue({
        data: { user: null, session: null },
        error: new AuthApiError('Signup failed', 500, 'unknown'),
      })

      renderSignupForm()
      await fillValidSignupForm(user)
      await completeCaptcha(user)
      await user.click(getSubmitButton())

      await findToastMessage(SIGNUP_USER_MESSAGES.unknown)
      await expectCaptchaNotVerified()
    })

    it('success resets captcha', async () => {
      const user = userEvent.setup()
      mockedSignUp.mockResolvedValue({
        data: { user: { identities: [{ id: 'identity-1' }] } },
        error: null,
      } as Awaited<ReturnType<typeof signUp>>)

      renderSignupForm()
      await fillValidSignupForm(user)
      await completeCaptcha(user)
      await user.click(getSubmitButton())

      await findToastMessage(SUCCESS_MESSAGE)
      await expectCaptchaNotVerified()
    })

    it('captcha expire resets and blocks submit', async () => {
      const user = userEvent.setup()
      renderSignupForm()

      await completeCaptcha(user)
      expectSubmitEnabled()

      await user.click(
        screen.getByRole('button', { name: 'Expire captcha challenge' }),
      )
      await expectCaptchaNotVerified()
    })
  })

  describe('Interruption/recovery (11)', () => {
    it('captcha widget error resets and shows connection toast', async () => {
      const user = userEvent.setup()
      renderSignupForm()

      await completeCaptcha(user)
      await user.click(
        screen.getByRole('button', { name: 'Captcha connection error' }),
      )

      await findToastMessage(SIGNUP_USER_MESSAGES.connection)
      await expectCaptchaNotVerified()
    })

    it('user can verify captcha again after error', async () => {
      const user = userEvent.setup()
      renderSignupForm()

      await completeCaptcha(user)
      await user.click(
        screen.getByRole('button', { name: 'Captcha connection error' }),
      )
      await findToastMessage(SIGNUP_USER_MESSAGES.connection)

      await completeCaptcha(user)
      expectSubmitEnabled()
    })
  })

  describe('Timing (9)', () => {
    it('submit disabled while submitting', async () => {
      const user = userEvent.setup()
      const deferred = createDeferred<Awaited<ReturnType<typeof signUp>>>()
      mockedSignUp.mockReturnValue(deferred.promise)

      renderSignupForm()
      await fillValidSignupForm(user)
      await completeCaptcha(user)
      await user.click(getSubmitButton())

      expect(
        screen.getByRole('button', { name: 'Creating account...' }),
      ).toBeDisabled()
      expectCaptchaNonInteractive()

      deferred.resolve({
        data: { user: { identities: [{ id: 'identity-1' }] } },
        error: null,
      } as Awaited<ReturnType<typeof signUp>>)
    })

    it('after submit completes, submit disabled until new captcha', async () => {
      const user = userEvent.setup()
      const deferred = createDeferred<Awaited<ReturnType<typeof signUp>>>()
      mockedSignUp.mockReturnValue(deferred.promise)

      renderSignupForm()
      await fillValidSignupForm(user)
      await completeCaptcha(user)
      await user.click(getSubmitButton())

      deferred.resolve({
        data: { user: { identities: [{ id: 'identity-1' }] } },
        error: null,
      } as Awaited<ReturnType<typeof signUp>>)

      await findToastMessage(SUCCESS_MESSAGE)
      await expectCaptchaNotVerified()
    })
  })

  describe('Concurrency (10)', () => {
    it('double submit does not fire duplicate API calls', async () => {
      const user = userEvent.setup()
      const deferred = createDeferred<Awaited<ReturnType<typeof signUp>>>()
      mockedSignUp.mockReturnValue(deferred.promise)

      renderSignupForm()
      await fillValidSignupForm(user)
      await completeCaptcha(user)

      const submitButton = getSubmitButton()
      await user.click(submitButton)
      await user.click(submitButton)

      expect(mockedSignUp).toHaveBeenCalledTimes(1)

      deferred.resolve({
        data: { user: { identities: [{ id: 'identity-1' }] } },
        error: null,
      } as Awaited<ReturnType<typeof signUp>>)

      await findToastMessage(SUCCESS_MESSAGE)
    })
  })
})
