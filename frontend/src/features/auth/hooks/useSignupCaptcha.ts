import { useCallback, useRef, useState } from 'react'
import type { TurnstileInstance } from '@marsidev/react-turnstile'

/** Manages Turnstile widget state and ref-based captcha token storage for signup. */
export function useSignupCaptcha() {
  const captchaTokenRef = useRef<string | null>(null)
  const turnstileRef = useRef<TurnstileInstance>(null)
  const onCaptchaErrorRef = useRef<(() => void) | undefined>(undefined)

  const [showWidget, setShowWidget] = useState(false)
  const [hasCaptchaToken, setHasCaptchaToken] = useState(false)

  /** Reads the current captcha token from ref at call time (avoids closure staleness). */
  function getCaptchaToken() {
    return captchaTokenRef.current
  }

  /** Clears token state and resets the Turnstile widget for a fresh challenge. */
  function resetCaptcha() {
    captchaTokenRef.current = null
    setHasCaptchaToken(false)
    setShowWidget(false)
    turnstileRef.current?.reset()
  }

  const registerCaptchaErrorHandler = useCallback((handler: () => void) => {
    onCaptchaErrorRef.current = handler
  }, [])

  function handleVerify(token: string) {
    captchaTokenRef.current = token
    setHasCaptchaToken(true)
  }

  function handleExpire() {
    resetCaptcha()
  }

  function handleError() {
    resetCaptcha()
    onCaptchaErrorRef.current?.()
  }

  return {
    captchaTokenRef,
    turnstileRef,
    showWidget,
    setShowWidget,
    hasCaptchaToken,
    getCaptchaToken,
    resetCaptcha,
    registerCaptchaErrorHandler,
    handleVerify,
    handleExpire,
    handleError,
  }
}

export type SignupCaptchaControls = ReturnType<typeof useSignupCaptcha>
