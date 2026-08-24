import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { login } from '@/features/auth/api/authApi'
import { getLoginErrorMessage } from '@/features/auth/utils/loginErrors'
import type { LoginFormData } from '@/features/auth/utils/loginSchema'

/** Coordinates login submission state, toast feedback, and post-auth navigation. */
export function useLogin() {
  const navigate = useNavigate()
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function submitLogin(formData: LoginFormData) {
    setIsSubmitting(true)

    try {
      const result = await login({
        email: formData.email,
        password: formData.password,
      })

      if (!result.ok) {
        const message = getLoginErrorMessage(result)
        toast.error(message ?? 'Invalid email or password')
        return
      }

      navigate('/auth/callback', {
        state: { cookie: result.data?.cookie ?? null },
      })
    } catch {
      toast.error('Unable to connect. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return { isSubmitting, submitLogin }
}
