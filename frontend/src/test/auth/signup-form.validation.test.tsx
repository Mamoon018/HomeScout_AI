import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { signUp } from '@/features/auth/api/authApi'
import { FIELD_MESSAGES } from '@/features/auth/utils/authFieldRules'
import {
  expectSubmitDisabled,
  expectSubmitEnabled,
  fillValidSignupForm,
  renderSignupForm,
  VALID_SIGNUP_PASSWORD,
} from '@/test/signupTestUtils'

// Captcha off here so the button state depends on the fields only.
vi.mock('@/features/auth/utils/captchaConfig', () => ({
  isCaptchaEnabled: () => false,
  getCaptchaSiteKey: () => 'test-site-key',
}))

vi.mock('@/features/auth/api/authApi', () => ({
  signUp: vi.fn(),
}))

const HINT = 'Fill in all fields correctly to continue'

function type(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

function popover() {
  return document.querySelector('[data-slot="field-rule-popover"]') as HTMLElement | null
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SignupForm field validation', () => {
  it('shows nothing while typing, and the rule once the user leaves the field', async () => {
    const user = userEvent.setup()
    renderSignupForm()
    const email = screen.getByLabelText('Email')

    await user.type(email, 'john@example.org')
    expect(screen.queryByText(FIELD_MESSAGES.emailDotCom)).not.toBeInTheDocument()

    await user.tab()
    expect(await screen.findByText(FIELD_MESSAGES.emailDotCom)).toBeInTheDocument()
    expect(email).toHaveAttribute('aria-invalid', 'true')
    expect(email).toHaveAttribute('aria-describedby', 'signup-email-rule')
  })

  it('shows no message for a field filled correctly', async () => {
    const user = userEvent.setup()
    renderSignupForm()

    await user.type(screen.getByLabelText('Email'), 'john@example.com')
    await user.tab()

    expect(popover()).toBeNull()
    expect(screen.getByLabelText('Email')).not.toHaveAttribute('aria-invalid')
  })

  it('updates live after the first blur and clears once fixed', async () => {
    const user = userEvent.setup()
    renderSignupForm()
    const age = screen.getByLabelText('Age')

    await user.type(age, '15')
    await user.tab()
    expect(await screen.findByText(FIELD_MESSAGES.age)).toBeInTheDocument()

    await user.clear(age)
    await user.type(age, '16')
    await waitFor(() => expect(screen.queryByText(FIELD_MESSAGES.age)).not.toBeInTheDocument())
    expect(age).not.toHaveAttribute('aria-invalid')
  })

  it('shows Required when a field is left empty', async () => {
    const user = userEvent.setup()
    renderSignupForm()

    await user.click(screen.getByLabelText('Full Name'))
    await user.tab()

    expect(await screen.findByText(FIELD_MESSAGES.required)).toBeInTheDocument()
  })

  it('lists each password rule with ✓/✗ for what is typed', async () => {
    const user = userEvent.setup()
    renderSignupForm()

    await user.type(screen.getByLabelText('Password'), 'password1')
    await user.tab()

    const list = await screen.findByRole('list', { name: 'Password rules' })
    const rows = within(list).getAllByRole('listitem')
    const state = Object.fromEntries(rows.map((row) => [row.textContent, row.dataset.met]))
    expect(state).toEqual({
      'At least 10 characters (missing)': 'false',
      'A lowercase letter (a–z) (done)': 'true',
      'An uppercase letter (A–Z) (missing)': 'false',
      'A digit (0–9) (done)': 'true',
      'A symbol, like ! @ # $ % (missing)': 'false',
    })
  })

  it('re-checks Confirm Password when Password changes', async () => {
    const user = userEvent.setup()
    renderSignupForm()

    type('Password', VALID_SIGNUP_PASSWORD)
    await user.click(screen.getByLabelText('Confirm Password'))
    type('Confirm Password', VALID_SIGNUP_PASSWORD)
    await user.tab()
    expect(screen.getByLabelText('Confirm Password')).not.toHaveAttribute('aria-invalid')

    type('Password', 'Password123?')
    await waitFor(() =>
      expect(screen.getByLabelText('Confirm Password')).toHaveAttribute('aria-invalid', 'true'),
    )
  })

  it('opens one popover at a time: the field the user just left', async () => {
    const user = userEvent.setup()
    renderSignupForm()

    await user.click(screen.getByLabelText('Full Name'))
    await user.tab() // leaves Full Name empty → its popover
    expect(popover()).toHaveAttribute('id', 'signup-fullName-rule')

    await user.type(screen.getByLabelText('Email'), 'x')
    await user.tab() // leaves Email invalid → Email's popover replaces it
    await waitFor(() => expect(popover()).toHaveAttribute('id', 'signup-email-rule'))
    expect(document.querySelectorAll('[data-slot="field-rule-popover"]')).toHaveLength(1)

    // Full Name is still marked invalid even without its popover.
    expect(screen.getByLabelText('Full Name')).toHaveAttribute('aria-invalid', 'true')
  })

  it('keeps submit disabled with a hint until every field is valid', async () => {
    const user = userEvent.setup()
    renderSignupForm()

    expectSubmitDisabled()
    expect(screen.getByText(HINT)).toBeVisible()

    await fillValidSignupForm(user)

    expectSubmitEnabled()
    expect(screen.getByText(HINT)).not.toBeVisible()
  })

  it('enables submit for values filled without any blur (autofill)', async () => {
    const user = userEvent.setup()
    renderSignupForm()

    // fillValidSignupForm sets the text inputs with change events only, as autofill does.
    await fillValidSignupForm(user)

    expectSubmitEnabled()
    expect(screen.getByLabelText('Password')).not.toHaveAttribute('aria-invalid')
  })

  it('sends the email without surrounding spaces', async () => {
    const user = userEvent.setup()
    vi.mocked(signUp).mockResolvedValue({
      data: { user: { identities: [{ id: 'identity-1' }] } },
      error: null,
    } as Awaited<ReturnType<typeof signUp>>)
    renderSignupForm()

    await fillValidSignupForm(user)
    type('Email', '  john@example.com  ')
    await user.click(screen.getByRole('button', { name: 'Create Account' }))

    await waitFor(() => expect(signUp).toHaveBeenCalled())
    expect(vi.mocked(signUp).mock.calls[0][0].email).toBe('john@example.com')
  })
})
