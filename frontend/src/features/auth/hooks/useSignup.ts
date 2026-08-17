import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { signUp } from '@/features/auth/api/authApi'
import type { SignupCaptchaControls } from '@/features/auth/hooks/useSignupCaptcha'
import {
  classifySignupError,
  isDuplicateSignupResponse,
  logSignupError,
  parseSignupAge,
  SIGNUP_USER_MESSAGES,
  validateSignupForm,
  type SignUpFormData,
} from '@/features/auth/utils/signupErrors'

export type { SignUpFormData }

const CAPTCHA_REQUIRED_MESSAGE =
  'Please complete the captcha challenge before signing up.'
const SUCCESS_MESSAGE = 'Successfully created an account for you!'

/** Coordinates signup submission state and toast feedback for the signup form. */
export function useSignup(captcha: SignupCaptchaControls) {
  const { getCaptchaToken, resetCaptcha, registerCaptchaErrorHandler } = captcha
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    registerCaptchaErrorHandler(() => {
      logSignupError('captcha-widget', 'connection', {
        source: 'turnstile',
      })
      toast.error(SIGNUP_USER_MESSAGES.connection)
    })
  }, [registerCaptchaErrorHandler])

  async function submitSignup(formData: SignUpFormData) {
    const captchaToken = getCaptchaToken()
    if (!captchaToken) {
      toast.error(CAPTCHA_REQUIRED_MESSAGE)
      return
    }

    const validationCategory = validateSignupForm(formData)
    if (validationCategory) {
      resetCaptcha()
      logSignupError('client-validation', validationCategory, formData)
      toast.error(SIGNUP_USER_MESSAGES[validationCategory])
      return
    }

    const parsedAge = parseSignupAge(formData.age)!
    setIsSubmitting(true)

    try {
      const { data, error } = await signUp({
        email: formData.email,
        password: formData.password,
        fullName: formData.fullName,
        age: parsedAge,
        country: formData.country,
        city: formData.city,
        zipCode: formData.zipCode,
        captchaToken: getCaptchaToken()!,
      })

      if (error) {
        resetCaptcha()
        const category = classifySignupError(error)
        logSignupError('supabase-signup', category, error)
        toast.error(SIGNUP_USER_MESSAGES[category])
        return
      }

      if (isDuplicateSignupResponse(data)) {
        resetCaptcha()
        logSignupError('supabase-signup', 'duplicate_credentials', data)
        toast.error(SIGNUP_USER_MESSAGES.duplicate_credentials)
        return
      }

      toast.success(SUCCESS_MESSAGE)
      resetCaptcha()
    } catch (error) {
      resetCaptcha()
      const category = classifySignupError(error)
      logSignupError('supabase-signup', category, error)
      toast.error(SIGNUP_USER_MESSAGES[category])
    } finally {
      setIsSubmitting(false)
    }
  }

  return { isSubmitting, submitSignup }
}
