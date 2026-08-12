import { createElement } from "react"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { Toaster } from "@/components/ui/sonner"
import SignupPage from "@/pages/SignupPage"
import { signUpWithEmail } from "@/features/auth/api/authApi"
import { supabase } from "@/lib/supabase"

const ERROR_MESSAGE = "email or password does not meet requirements, try again!"
const SUCCESS_MESSAGE = "Successfully created an account for you!"

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      signUp: vi.fn(),
    },
  },
}))

function renderSignupRoute(initialPath = "/signup") {
  const view = render(
    createElement(
      MemoryRouter,
      { initialEntries: [initialPath] },
      createElement(Routes, null, createElement(Route, { path: "/signup", element: createElement(SignupPage) })),
      createElement(Toaster)
    )
  )

  return {
    ...view,
    page: within(view.container),
  }
}

async function fillSignupForm(user, page, overrides = {}) {
  const email = overrides.email ?? "user@example.com"
  const password = overrides.password ?? "securepass123"
  const confirmPassword = overrides.confirmPassword ?? password

  await user.type(page.getByLabelText(/^email$/i), email)
  await user.type(page.getByLabelText(/^password$/i), password)
  await user.type(page.getByLabelText(/confirm password/i), confirmPassword)
}

describe("signup page — integration / contract", () => {
  beforeEach(() => {
    supabase.auth.signUp.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("should_render_brand_heading_and_form_when_user_visits_signup", () => {
    renderSignupRoute()

    expect(screen.getByText("HomeScout AI")).toBeInTheDocument()
    expect(
      screen.getByRole("heading", {
        name: /build team of agents for your home scout/i,
      })
    ).toBeInTheDocument()
    expect(screen.getByLabelText(/^email$/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument()
  })

  it("should_mask_password_fields_by_default_when_signup_form_is_displayed", () => {
    renderSignupRoute()

    expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "password")
    expect(screen.getByLabelText(/confirm password/i)).toHaveAttribute(
      "type",
      "password"
    )
  })

  it("should_reveal_password_fields_when_show_password_is_checked", async () => {
    const user = userEvent.setup()
    const { page } = renderSignupRoute()

    await user.click(page.getByRole("checkbox", { name: /show password/i }))

    expect(page.getByLabelText(/^password$/i)).toHaveAttribute("type", "text")
    expect(page.getByLabelText(/confirm password/i)).toHaveAttribute("type", "text")
  })
})

describe("signup submission — integration / state management", () => {
  beforeEach(() => {
    supabase.auth.signUp.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("should_disable_inputs_and_show_loading_spinner_while_submitting", async () => {
    let resolveSignup
    supabase.auth.signUp.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSignup = () =>
            resolve({ data: { user: { id: "1" } }, error: null })
        })
    )

    const user = userEvent.setup()
    const { page } = renderSignupRoute()
    await fillSignupForm(user, page)

    await user.click(page.getByRole("button", { name: /create account/i }))

    expect(page.getByRole("button", { name: /creating account/i })).toBeDisabled()
    expect(page.getByLabelText(/^email$/i)).toBeDisabled()
    expect(page.getByLabelText(/^password$/i)).toBeDisabled()
    expect(page.getByLabelText(/confirm password/i)).toBeDisabled()

    resolveSignup()

    await waitFor(() => {
      expect(page.getByRole("button", { name: /create account/i })).toBeEnabled()
    })
  })

  it("should_show_success_toast_and_clear_passwords_when_signup_succeeds", async () => {
    supabase.auth.signUp.mockResolvedValue({
      data: { user: { id: "user-1" } },
      error: null,
    })

    const user = userEvent.setup()
    const { page } = renderSignupRoute()
    await fillSignupForm(user, page, { email: "new@example.com", password: "validpass99" })
    await user.click(page.getByRole("button", { name: /create account/i }))

    expect(await screen.findByText(SUCCESS_MESSAGE)).toBeInTheDocument()
    expect(supabase.auth.signUp).toHaveBeenCalledWith({
      email: "new@example.com",
      password: "validpass99",
    })
    expect(page.getByLabelText(/^password$/i)).toHaveValue("")
    expect(page.getByLabelText(/confirm password/i)).toHaveValue("")
    expect(page.getByText("HomeScout AI")).toBeInTheDocument()
  })

  it("should_show_error_toast_when_supabase_signup_fails", async () => {
    supabase.auth.signUp.mockResolvedValue({
      data: null,
      error: { message: "User already registered", code: "user_exists" },
    })

    const user = userEvent.setup()
    const { page } = renderSignupRoute()
    await fillSignupForm(user, page)
    await user.click(page.getByRole("button", { name: /create account/i }))

    expect(await screen.findByText(ERROR_MESSAGE)).toBeInTheDocument()
    expect(screen.queryByText(SUCCESS_MESSAGE)).not.toBeInTheDocument()
  })

  it("should_show_error_toast_and_skip_supabase_when_passwords_do_not_match", async () => {
    const user = userEvent.setup()
    const { page } = renderSignupRoute()
    await fillSignupForm(user, page, {
      password: "password-one",
      confirmPassword: "password-two",
    })
    await user.click(page.getByRole("button", { name: /create account/i }))

    expect(await screen.findByText(ERROR_MESSAGE)).toBeInTheDocument()
    expect(supabase.auth.signUp).not.toHaveBeenCalled()
  })
})

describe("signUpWithEmail — unit / error handling", () => {
  beforeEach(() => {
    supabase.auth.signUp.mockReset()
  })

  it("should_return_supabase_error_when_signUp_fails", async () => {
    supabase.auth.signUp.mockResolvedValue({
      data: { user: null },
      error: { message: "Invalid login credentials", code: "invalid_credentials" },
    })

    const result = await signUpWithEmail({
      email: "bad@example.com",
      password: "short",
    })

    expect(result.error).toMatchObject({
      message: "Invalid login credentials",
      code: "invalid_credentials",
    })
    expect(result.data).toEqual({ user: null })
  })
})
