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
