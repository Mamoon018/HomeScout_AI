import { apiFetch, fetchJson } from '@/lib/apiClient'
import { supabase } from '@/lib/supabase'
import { isCaptchaEnabled } from '@/features/auth/utils/captchaConfig'

export type SignUpParams = {
  email: string
  password: string
  fullName: string
  age: number
  country: string
  city: string
  zipCode: string
  captchaToken?: string
}

export type LoginParams = {
  email: string
  password: string
  captchaToken?: string
}

export type LoginApiData = {
  message?: string
  error?: string
  code?: string
  user_id?: string
  user_name?: string | null
}

export type AuthApiResponse<T> = {
  ok: boolean
  status: number
  data: T | null
  aborted?: boolean
  networkError?: boolean
}

export type WelcomeApiData = {
  message?: string
  error?: string
  code?: string
}

export type RefreshApiData = {
  message?: string
  error?: string
}

export type LoginApiResponse = AuthApiResponse<LoginApiData>
export type WelcomeApiResponse = AuthApiResponse<WelcomeApiData>
export type RefreshApiResponse = AuthApiResponse<RefreshApiData>

const LOGIN_PATH = '/api/auth/login'
const REFRESH_PATH = '/auth/refresh'
const USER_WELCOME_PATH = '/api/user_welcome'

let welcomeInFlight: Promise<WelcomeApiResponse> | null = null

/** Registers a new user via Supabase Auth browser client. */
export async function signUp(params: SignUpParams) {
  // age must be a JSON number (not string) so auth metadata stores a numeric value.
  const age = Math.trunc(params.age)
  const captchaRequired = isCaptchaEnabled()

  return supabase.auth.signUp({
    email: params.email,
    password: params.password,
    options: {
      ...(captchaRequired ? { captchaToken: params.captchaToken } : {}),
      data: {
        full_name: params.fullName,
        age,
        country: params.country,
        city: params.city,
        zip_code: params.zipCode,
      },
    },
  })
}

/** Authenticates via a same-origin relative path so Vite can proxy the cookie. */
export async function login(params: LoginParams): Promise<LoginApiResponse> {
  const captchaRequired = isCaptchaEnabled()

  return apiFetch<LoginApiData>(
    LOGIN_PATH,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: params.email,
        password: params.password,
        ...(captchaRequired ? { captcha_token: params.captchaToken } : {}),
      }),
    },
    { skipRefresh: true },
  )
}

/** Exchanges the path-scoped refresh cookie for rotated session cookies. */
export async function refreshSession(): Promise<RefreshApiResponse> {
  return fetchJson<RefreshApiData>(REFRESH_PATH, {
    method: 'POST',
  })
}

/** Loads the identity-scoped welcome message using the HttpOnly access-token cookie. */
export async function getUserWelcome(): Promise<WelcomeApiResponse> {
  if (welcomeInFlight) {
    return welcomeInFlight
  }

  welcomeInFlight = apiFetch<WelcomeApiData>(USER_WELCOME_PATH, {
    method: 'GET',
  }).finally(() => {
    welcomeInFlight = null
  })

  return welcomeInFlight
}

/** Resets welcome dedup state — for tests only. */
export function resetWelcomeStateForTests(): void {
  welcomeInFlight = null
}
