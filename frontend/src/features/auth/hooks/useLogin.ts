import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { login } from '@/features/auth/api/authApi'
import type { SignupCaptchaControls } from '@/features/auth/hooks/useSignupCaptcha'
import { saveAuthUser } from '@/features/auth/utils/authUserStore'
import { isCaptchaEnabled } from '@/features/auth/utils/captchaConfig'
import { getLoginErrorMessage } from '@/features/auth/utils/loginErrors'
import type { LoginFormData } from '@/features/auth/utils/loginSchema'

const CAPTCHA_REQUIRED_MESSAGE =
  'Please complete the captcha challenge before signing in.'

/** Coordinates login submission state, toast feedback, and post-auth navigation. */
export function useLogin(captcha: SignupCaptchaControls) {
  const navigate = useNavigate()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const captchaRequired = isCaptchaEnabled()
  const { getCaptchaToken, resetCaptcha, registerCaptchaErrorHandler } = captcha

  useEffect(() => {
    if (!captchaRequired) {
      return
    }

    registerCaptchaErrorHandler(() => {
      toast.error('Unable to connect. Please try again.')
    })
  }, [captchaRequired, registerCaptchaErrorHandler])

  async function submitLogin(formData: LoginFormData) {
    if (captchaRequired) {
      const captchaToken = getCaptchaToken()
      if (!captchaToken) {
        toast.error(CAPTCHA_REQUIRED_MESSAGE)
        return
      }
    }

    setIsSubmitting(true)

    try {
      const result = await login({
        email: formData.email,
        password: formData.password,
        captchaToken: captchaRequired ? getCaptchaToken()! : undefined,
      })

      if (!result.ok) {
        if (captchaRequired) {
          resetCaptcha()
        }
        const message = getLoginErrorMessage(result)
        toast.error(message ?? 'Invalid email or password')
        return
      }

      const userId = result.data?.user_id
      if (userId) {
        saveAuthUser({
          user_id: userId,
          user_name: result.data?.user_name ?? null,
        })
      }

      navigate('/home', { replace: true })
    } catch {
      if (captchaRequired) {
        resetCaptcha()
      }
      toast.error('Unable to connect. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return { isSubmitting, submitLogin }
}
