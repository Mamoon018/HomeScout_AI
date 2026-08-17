import { isAuthApiError, type AuthResponse } from '@supabase/supabase-js'

export type SignUpFormData = {
  fullName: string
  email: string
  age: string
  country: string
  city: string
  zipCode: string
  password: string
  confirmPassword: string
}

export type SignupErrorCategory =
  | 'duplicate_credentials'
  | 'connection'
  | 'validation'
  | 'rate_limit'
  | 'unknown'

/** Safe user-facing messages — never expose raw API error details in the UI. */
export const SIGNUP_USER_MESSAGES: Record<SignupErrorCategory, string> = {
  duplicate_credentials: 'Email or Password already exist',
  connection: 'There is a problem in your connection, Please try again!',
  validation: 'Input fields is not correct',
  rate_limit: 'Too many requests, try again after some time!',
  unknown: 'Something went wrong. Please try again.',
}

const DUPLICATE_CREDENTIAL_CODES = new Set([
  'user_already_exists',
  'email_exists',
  'phone_exists',
  'identity_already_exists',
])

const RATE_LIMIT_CODES = new Set([
  'over_request_rate_limit',
  'over_email_send_rate_limit',
  'over_sms_send_rate_limit',
])

const VALIDATION_CODES = new Set([
  'validation_failed',
  'weak_password',
  'email_address_invalid',
  'captcha_failed',
])

const CONNECTION_CODES = new Set(['request_timeout'])

const CONNECTION_HTTP_STATUSES = new Set([0, 502, 503, 504])

/** Parses age from form input into a positive integer for database int8 storage. */
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

/** Runs client-side checks before the signup API call. Returns a category when invalid. */
export function validateSignupForm(
  formData: SignUpFormData,
): SignupErrorCategory | null {
  const requiredFields = [
    formData.fullName,
    formData.email,
    formData.country,
    formData.city,
    formData.zipCode,
  ]

  if (requiredFields.some((value) => value.trim() === '')) {
    return 'validation'
  }

  if (parseSignupAge(formData.age) === null) {
    return 'validation'
  }

  if (formData.password.length < 8) {
    return 'validation'
  }

  if (formData.password !== formData.confirmPassword) {
    return 'validation'
  }

  return null
}

function isNetworkError(error: unknown) {
  if (!(error instanceof Error)) {
    return false
  }

  if (error.name === 'TypeError') {
    return true
  }

  return /failed to fetch|network error|load failed/i.test(error.message)
}

/** Maps Supabase or thrown errors to a signup error category for user messaging. */
export function classifySignupError(error: unknown): SignupErrorCategory {
  if (isNetworkError(error)) {
    return 'connection'
  }

  if (!isAuthApiError(error)) {
    return 'unknown'
  }

  const errorCode = error.code ?? ''

  if (DUPLICATE_CREDENTIAL_CODES.has(errorCode)) {
    return 'duplicate_credentials'
  }

  if (RATE_LIMIT_CODES.has(errorCode) || error.status === 429) {
    return 'rate_limit'
  }

  if (VALIDATION_CODES.has(errorCode) || error.status === 422) {
    return 'validation'
  }

  if (CONNECTION_CODES.has(errorCode) || CONNECTION_HTTP_STATUSES.has(error.status)) {
    return 'connection'
  }

  return 'unknown'
}

/**
 * Detects obfuscated duplicate signup when email confirmation is enabled.
 * Supabase may return a user with an empty identities array instead of user_already_exists.
 */
export function isDuplicateSignupResponse(data: AuthResponse['data']) {
  const user = data?.user
  if (!user) {
    return false
  }

  return Array.isArray(user.identities) && user.identities.length === 0
}

/** Logs structured signup error details for developer debugging (not shown to users). */
export function logSignupError(
  context: string,
  category: SignupErrorCategory,
  details: unknown,
) {
  const payload: Record<string, unknown> = {
    context,
    category,
    details,
  }

  if (isAuthApiError(details)) {
    payload.code = details.code
    payload.status = details.status
    payload.message = details.message
  }

  console.error('[signup]', payload)
}
