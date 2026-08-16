import { useState } from 'react'
import { toast } from 'sonner'
import { signUp } from '@/features/auth/api/authApi'

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

const ERROR_MESSAGE = 'email or password does not meet requirements, try again!'
const SUCCESS_MESSAGE = 'Successfully created an account for you!'

/** Coordinates signup submission state and toast feedback for the signup form. */
export function useSignup() {
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function submitSignup(formData: SignUpFormData) {
    setIsSubmitting(true)

    try {
      const { error } = await signUp({
        email: formData.email,
        password: formData.password,
        fullName: formData.fullName,
        age: formData.age,
        country: formData.country,
        city: formData.city,
        zipCode: formData.zipCode,
      })

      if (error) {
        toast.error(ERROR_MESSAGE)
        return
      }

      toast.success(SUCCESS_MESSAGE)
    } catch {
      toast.error(ERROR_MESSAGE)
    } finally {
      setIsSubmitting(false)
    }
  }

  return { isSubmitting, submitSignup }
}
