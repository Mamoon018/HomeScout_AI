import { z } from 'zod'

/**
 * Field rules shared by the sign-in and sign-up forms, checked in the browser before anything
 * reaches the server.
 *
 * Password rules MUST match Supabase → Authentication → Passwords on the hosted project
 * (and `backend/supabase/config.toml` locally): minimum 10 characters, with lowercase,
 * uppercase, digits and symbols. Server-only checks (email already registered, wrong
 * password, rate limits) are not repeated here.
 */

export const MIN_PASSWORD_LENGTH = 10

/** The symbol set Supabase accepts for its "symbols" password requirement. */
export const PASSWORD_SYMBOLS = '!@#$%^&*()_+-=[]{};\'\\:"|<>?,./`~'

export const MIN_SIGNUP_AGE = 16

export const FIELD_MESSAGES = {
  required: 'This field is required.',
  emailFormat: 'Enter a valid email address, like name@example.com.',
  emailDotCom: 'Email must contain @ and end with .com.',
  age: `Age must be a whole number, ${MIN_SIGNUP_AGE} or older.`,
  passwordRules: 'Password must meet every rule below.',
  passwordMismatch: 'Passwords must match.',
} as const

export type PasswordRuleResult = { id: string; label: string; met: boolean }

const PASSWORD_RULES: { id: string; label: string; test: (password: string) => boolean }[] = [
  {
    id: 'length',
    label: `At least ${MIN_PASSWORD_LENGTH} characters`,
    test: (password) => password.length >= MIN_PASSWORD_LENGTH,
  },
  { id: 'lowercase', label: 'A lowercase letter (a–z)', test: (password) => /[a-z]/.test(password) },
  { id: 'uppercase', label: 'An uppercase letter (A–Z)', test: (password) => /[A-Z]/.test(password) },
  { id: 'digit', label: 'A digit (0–9)', test: (password) => /\d/.test(password) },
  {
    id: 'symbol',
    label: 'A symbol, like ! @ # $ %',
    test: (password) => [...password].some((char) => PASSWORD_SYMBOLS.includes(char)),
  },
]

const emailFormat = z.email()

/** Each password rule and whether the given password meets it (drives the ✓/✗ checklist). */
export function checkPasswordRules(password: string): PasswordRuleResult[] {
  return PASSWORD_RULES.map(({ id, label, test }) => ({ id, label, met: test(password) }))
}

export function isStrongPassword(password: string): boolean {
  return PASSWORD_RULES.every(({ test }) => test(password))
}

/** The email as it is checked and sent: surrounding spaces removed. */
export function normalizeEmail(value: string): string {
  return value.trim()
}

/** Returns the message for an empty value, or null when something was entered. */
export function validateRequired(value: string): string | null {
  return value.trim() === '' ? FIELD_MESSAGES.required : null
}

/** Valid email format, with @ and a domain ending in .com (any letter case). */
export function validateEmail(value: string): string | null {
  const email = normalizeEmail(value).toLowerCase()
  if (email === '') {
    return FIELD_MESSAGES.required
  }
  if (!email.includes('@') || !email.endsWith('.com')) {
    return FIELD_MESSAGES.emailDotCom
  }
  if (!emailFormat.safeParse(email).success) {
    return FIELD_MESSAGES.emailFormat
  }
  return null
}

/** Sign-in email: required and a valid email format; any domain (no .com rule). */
export function validateLoginEmail(value: string): string | null {
  const email = normalizeEmail(value)
  if (email === '') {
    return FIELD_MESSAGES.required
  }
  return emailFormat.safeParse(email).success ? null : FIELD_MESSAGES.emailFormat
}

/** Parses age input into a positive whole number, or null when it is not one. */
export function parseSignupAge(value: string): number | null {
  const trimmed = value.trim()
  if (trimmed === '' || !/^\d+$/.test(trimmed)) {
    return null
  }

  const parsed = Number.parseInt(trimmed, 10)
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    return null
  }

  return parsed
}

/** Age must be a whole number of at least MIN_SIGNUP_AGE. */
export function validateAge(value: string): string | null {
  if (value.trim() === '') {
    return FIELD_MESSAGES.required
  }
  const age = parseSignupAge(value)
  return age !== null && age >= MIN_SIGNUP_AGE ? null : FIELD_MESSAGES.age
}

/** A new password (sign-up) must meet every Supabase password rule. */
export function validateNewPassword(password: string): string | null {
  if (password === '') {
    return FIELD_MESSAGES.required
  }
  return isStrongPassword(password) ? null : FIELD_MESSAGES.passwordRules
}

/** Confirm Password meets the same rules and matches Password. */
export function validateConfirmPassword(confirmPassword: string, password: string): string | null {
  const ruleError = validateNewPassword(confirmPassword)
  if (ruleError) {
    return ruleError
  }
  return confirmPassword === password ? null : FIELD_MESSAGES.passwordMismatch
}

/** Sign-in only needs a password; older accounts may predate the strength rules. */
export function validateLoginPassword(password: string): string | null {
  return password === '' ? FIELD_MESSAGES.required : null
}
