import { supabase } from "@/lib/supabase"

/**
 * Registers a new user via Supabase Auth email/password signup.
 */
export async function signUpWithEmail({ email, password }) {
  const { data, error } = await supabase.auth.signUp({ email, password })

  if (error) {
    console.error("[auth/signUpWithEmail] Supabase signup failed:", {
      message: error.message,
      code: error.code,
      status: error.status,
    })
  }

  return { data, error }
}
