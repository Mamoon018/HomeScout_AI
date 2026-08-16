import { supabase } from '@/lib/supabase'

export type SignUpParams = {
  email: string
  password: string
  fullName: string
  age: string
  country: string
  city: string
  zipCode: string
}

/** Registers a new user via Supabase Auth browser client. */
export async function signUp(params: SignUpParams) {
  return supabase.auth.signUp({
    email: params.email,
    password: params.password,
    options: {
      data: {
        full_name: params.fullName,
        age: params.age,
        country: params.country,
        city: params.city,
        zip_code: params.zipCode,
      },
    },
  })
}
