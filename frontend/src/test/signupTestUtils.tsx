import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { SignupForm } from '@/components/signup-form'
import { Toaster } from '@/components/ui/sonner'

export function renderSignupForm() {
  return render(
    <>
      <SignupForm />
      <Toaster />
    </>,
  )
}

export function getSubmitButton() {
  return screen.getByRole('button', { name: 'Create Account' })
}

export function expectSubmitDisabled() {
  expect(getSubmitButton()).toBeDisabled()
}

export function expectSubmitEnabled() {
  expect(getSubmitButton()).not.toBeDisabled()
}

export async function expectCaptchaNotVerified() {
  expectSubmitDisabled()
  await waitFor(() => {
    expect(
      screen.getByRole('button', { name: 'Verify captcha' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Complete captcha challenge' }),
    ).not.toBeInTheDocument()
  })
}

export async function openCaptchaWidget(user: UserEvent) {
  await user.click(screen.getByRole('button', { name: 'Verify captcha' }))
}

export async function completeCaptcha(user: UserEvent) {
  await openCaptchaWidget(user)
  await user.click(
    screen.getByRole('button', { name: 'Complete captcha challenge' }),
  )
}

function setInputValue(element: HTMLElement, value: string) {
  fireEvent.change(element, { target: { value } })
}

export async function fillValidSignupForm(user: UserEvent) {
  setInputValue(screen.getByLabelText('Full Name'), 'John Doe')
  setInputValue(screen.getByLabelText('Email'), 'john@example.com')
  setInputValue(screen.getByLabelText('Age'), '25')

  await user.click(screen.getByRole('combobox', { name: 'Country' }))
  await user.click(await screen.findByRole('option', { name: 'United States' }))

  await user.click(screen.getByRole('combobox', { name: 'City' }))
  await user.click(await screen.findByRole('option', { name: 'New York' }))

  setInputValue(screen.getByLabelText('Zip code'), '10001')
  setInputValue(screen.getByLabelText('Password'), 'password123')
  setInputValue(screen.getByLabelText('Confirm Password'), 'password123')
}

export async function fillSignupFormWithPasswordMismatch(user: UserEvent) {
  await fillValidSignupForm(user)
  setInputValue(screen.getByLabelText('Confirm Password'), 'different-password')
}

export async function findToastMessage(message: string) {
  const matches = await screen.findAllByText(message)
  return matches[matches.length - 1]
}

export function getCaptchaFieldContainer() {
  const verifyButton = screen.queryByRole('button', { name: 'Verify captcha' })
  const completeButton = screen.queryByRole('button', {
    name: 'Complete captcha challenge',
  })
  const anchor = verifyButton ?? completeButton
  if (!anchor) {
    throw new Error('Captcha controls not found')
  }
  return anchor.closest('[data-slot="field"]') ?? anchor.parentElement!
}

export function expectCaptchaNonInteractive() {
  const mockTurnstile = screen.getByTestId('mock-turnstile')
  const widgetArea = mockTurnstile.parentElement
  expect(widgetArea).toHaveClass('pointer-events-none')
}
