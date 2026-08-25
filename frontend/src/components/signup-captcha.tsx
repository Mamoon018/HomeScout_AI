import { Turnstile } from '@marsidev/react-turnstile'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription } from '@/components/ui/field'
import type { SignupCaptchaControls } from '@/features/auth/hooks/useSignupCaptcha'
import { getCaptchaSiteKey } from '@/features/auth/utils/captchaConfig'
import { cn } from '@/lib/utils'

type SignupCaptchaProps = {
  disabled?: boolean
  captcha: SignupCaptchaControls
  description?: string
}

/** Renders the Turnstile captcha trigger button and widget for auth forms. */
export function SignupCaptcha({
  disabled = false,
  captcha,
  description = 'Complete the captcha challenge to enable account creation.',
}: SignupCaptchaProps) {
  const {
    showWidget,
    setShowWidget,
    turnstileRef,
    handleVerify,
    handleExpire,
    handleError,
  } = captcha

  return (
    <Field>
      {!showWidget ? (
        <Button
          type="button"
          variant="outline"
          className="w-full"
          disabled={disabled}
          onClick={() => setShowWidget(true)}
        >
          Verify captcha
        </Button>
      ) : (
        <div
          className={cn(
            'flex flex-col gap-2',
            disabled && 'pointer-events-none opacity-50',
          )}
        >
          <Turnstile
            ref={turnstileRef}
            siteKey={getCaptchaSiteKey()}
            onSuccess={handleVerify}
            onExpire={handleExpire}
            onError={handleError}
          />
        </div>
      )}
      <FieldDescription>{description}</FieldDescription>
    </Field>
  )
}
