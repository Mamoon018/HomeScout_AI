import { useState } from "react"
import { toast } from "sonner"
import { signUpWithEmail } from "@/features/auth/api/authApi"

const ERROR_MESSAGE = "email or password does not meet requirements, try again!"
const SUCCESS_MESSAGE = "Successfully created an account for you!"

/**
 * Manages signup form state and coordinates Supabase registration with toast feedback.
 */
export function useSignup() {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()

    if (password !== confirmPassword) {
      console.error("[auth/signup] Validation failed: password confirmation mismatch")
      toast.error(ERROR_MESSAGE)
      return
    }

    setIsSubmitting(true)

    try {
      const { error } = await signUpWithEmail({ email, password })

      if (error) {
        toast.error(ERROR_MESSAGE)
        return
      }

      toast.success(SUCCESS_MESSAGE)
      setPassword("")
      setConfirmPassword("")
    } catch (unexpectedError) {
      console.error("[auth/signup] Unexpected signup error:", unexpectedError)
      toast.error(ERROR_MESSAGE)
    } finally {
      setIsSubmitting(false)
    }
  }

  return {
    email,
    setEmail,
    password,
    setPassword,
    confirmPassword,
    setConfirmPassword,
    showPassword,
    setShowPassword,
    isSubmitting,
    handleSubmit,
  }
}
