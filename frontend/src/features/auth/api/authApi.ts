import { supabase } from '@/lib/supabase'

export type SignUpParams = {
  email: string
  password: string
  fullName: string
  age: number
  country: string
  city: string
  zipCode: string
  captchaToken: string
}

export type LoginParams = {
  email: string
  password: string
  captchaToken: string
}

export type LoginApiData = {
  message?: string
  error?: string
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

export type LoginApiResponse = AuthApiResponse<LoginApiData>

const AUTH_API_TIMEOUT_MS = 15000
const LOGIN_PATH = '/api/auth/login'

type SameOriginFetchResult<T> = AuthApiResponse<T>

async function fetchSameOriginJson<T>(
  path: string,
  init: RequestInit,
): Promise<SameOriginFetchResult<T>> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), AUTH_API_TIMEOUT_MS)

  try {
    const response = await fetch(path, {
      ...init,
      credentials: 'include',
      signal: controller.signal,
    })

    let data: T | null = null
    try {
      data = (await response.json()) as T
    } catch {
      data = null
    }

    return {
      ok: response.ok,
      status: response.status,
      data,
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return {
        ok: false,
        status: 0,
        data: null,
        aborted: true,
      }
    }

    if (error instanceof TypeError) {
      return {
        ok: false,
        status: 0,
        data: null,
        networkError: true,
      }
    }

    throw error
  } finally {
    clearTimeout(timeout)
  }
}

/** Registers a new user via Supabase Auth browser client. */
export async function signUp(params: SignUpParams) {
  // age must be a JSON number (not string) so auth metadata stores a numeric value.
  const age = Math.trunc(params.age)

  return supabase.auth.signUp({
    email: params.email,
    password: params.password,
    options: {
      captchaToken: params.captchaToken,
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
  return fetchSameOriginJson<LoginApiData>(LOGIN_PATH, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: params.email,
      password: params.password,
      captcha_token: params.captchaToken,
    }),
  })
}
