import { render, screen } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { LoginForm } from '@/components/login-form'
import { Toaster } from '@/components/ui/sonner'

export function renderLoginForm() {
  return render(
    <MemoryRouter>
      <LoginForm />
      <Toaster />
    </MemoryRouter>,
  )
}

export function getSubmitButton() {
  return screen.getByRole('button', { name: 'Sign In' })
}

export function getPasswordInput() {
  return screen.getByLabelText('Password')
}

export async function fillValidLoginForm(user: UserEvent) {
  await user.type(screen.getByLabelText('Email'), 'demo@homescout.ai')
  await user.type(getPasswordInput(), 'password123')
}

export async function openLoginCaptchaWidget(user: UserEvent) {
  await user.click(screen.getByRole('button', { name: 'Verify captcha' }))
}

export async function completeLoginCaptcha(user: UserEvent) {
  await openLoginCaptchaWidget(user)
  await user.click(
    screen.getByRole('button', { name: 'Complete captcha challenge' }),
  )
}

export async function fillValidLoginFormWithCaptcha(user: UserEvent) {
  await fillValidLoginForm(user)
  await completeLoginCaptcha(user)
}

export async function findToastMessage(message: string) {
  const matches = await screen.findAllByText(message)
  return matches[matches.length - 1]
}
