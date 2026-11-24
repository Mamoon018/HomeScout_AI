import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowBigUpDash, Loader2 } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useLogin } from '@/features/auth/hooks/useLogin'
import { useSignupCaptcha } from '@/features/auth/hooks/useSignupCaptcha'
import { loginSchema, type LoginFormData } from '@/features/auth/utils/loginSchema'
import { FieldRulePopover } from '@/features/auth/components/field-rule-popover'
import { SignupCaptcha } from '@/features/auth/components/signup-captcha'
import { SubmitHint } from '@/features/auth/components/submit-hint'
import { isCaptchaEnabled } from '@/features/auth/utils/captchaConfig'

const EMAIL_RULE_ID = 'login-email-rule'
const PASSWORD_RULE_ID = 'login-password-rule'
const SUBMIT_HINT_ID = 'login-submit-hint'

/**
 * Sign-in card. react-hook-form checks each field against loginSchema (shared rules) once the
 * user leaves it, then live while typing; useLogin submits.
 *
 * Data path: input → LoginForm → loginSchema (authFieldRules) → popovers / submit button
 *   → submit → useLogin → authApi.login → FastAPI → useLogin (toasts, redirect)
 */
export function LoginForm({
  className,
  ...props
}: React.ComponentProps<'div'>) {
  const captcha = useSignupCaptcha()
  const { isSubmitting, submitLogin } = useLogin(captcha)
  const [showPassword, setShowPassword] = useState(false)
  // Caps Lock is a common, invisible cause of "wrong password" — warn before submit.
  const [capsLockOn, setCapsLockOn] = useState(false)
  const syncCapsLock = (event: React.KeyboardEvent<HTMLInputElement>) =>
    setCapsLockOn(event.getModifierState('CapsLock'))
  const passwordInputType = showPassword ? 'text' : 'password'

  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    // Check a field when the user leaves it, then on every change after that.
    mode: 'onTouched',
    defaultValues: {
      email: '',
      password: '',
    },
  })

  // Popovers point at the inputs, so keep our own element refs beside react-hook-form's.
  const emailAnchor = useRef<HTMLInputElement>(null)
  const passwordAnchor = useRef<HTMLInputElement>(null)
  const emailField = register('email')
  const passwordField = register('password')
  const passwordDescribedBy =
    [errors.password ? PASSWORD_RULE_ID : null, capsLockOn ? 'caps-lock-hint' : null]
      .filter(Boolean)
      .join(' ') || undefined

  return (
    <div className={cn('flex flex-col gap-6', className)} {...props}>
      <Card data-slot="auth-card" className="border-border/60 bg-card">
        <CardHeader className="text-center">
          <CardTitle className="text-xl">Welcome back</CardTitle>
          <CardDescription>
            Enter your email and password to sign in
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(submitLogin)}>
            <FieldGroup>
              <Field data-invalid={!!errors.email}>
                <FieldLabel htmlFor="login-email">Email</FieldLabel>
                <Input
                  id="login-email"
                  type="email"
                  placeholder="m@example.com"
                  autoComplete="email"
                  disabled={isSubmitting}
                  aria-invalid={!!errors.email}
                  aria-describedby={errors.email ? EMAIL_RULE_ID : undefined}
                  {...emailField}
                  ref={(element) => {
                    emailField.ref(element)
                    emailAnchor.current = element
                  }}
                />
                <FieldRulePopover
                  id={EMAIL_RULE_ID}
                  open={!!errors.email}
                  anchor={emailAnchor}
                  message={errors.email?.message ?? ''}
                />
              </Field>
              <Field data-invalid={!!errors.password}>
                <FieldLabel htmlFor="login-password">Password</FieldLabel>
                <Input
                  id="login-password"
                  type={passwordInputType}
                  autoComplete="current-password"
                  disabled={isSubmitting}
                  aria-invalid={!!errors.password}
                  aria-describedby={passwordDescribedBy}
                  onKeyDown={syncCapsLock}
                  onKeyUp={syncCapsLock}
                  {...passwordField}
                  ref={(element) => {
                    passwordField.ref(element)
                    passwordAnchor.current = element
                  }}
                />
                <FieldRulePopover
                  id={PASSWORD_RULE_ID}
                  open={!!errors.password}
                  anchor={passwordAnchor}
                  message={errors.password?.message ?? ''}
                />
                {capsLockOn ? (
                  <p
                    id="caps-lock-hint"
                    data-slot="caps-lock-hint"
                    role="status"
                    className="flex items-center gap-1.5 text-xs text-muted-foreground"
                  >
                    <ArrowBigUpDash aria-hidden="true" className="size-3.5" />
                    Caps Lock is on
                  </p>
                ) : null}
                <div className="flex items-center gap-2 pt-2">
                  <Checkbox
                    id="show-password"
                    checked={showPassword}
                    onCheckedChange={(checked) =>
                      setShowPassword(checked === true)
                    }
                    disabled={isSubmitting}
                  />
                  <Label
                    htmlFor="show-password"
                    data-slot="auth-show-password"
                    className="text-sm font-normal text-muted-foreground"
                  >
                    Show password
                  </Label>
                </div>
              </Field>
              <SignupCaptcha
                disabled={isSubmitting}
                captcha={captcha}
                description="Complete the captcha challenge to enable sign in."
              />
              <Field>
                <Button
                  type="submit"
                  data-slot="auth-submit"
                  className="w-full"
                  disabled={
                    isSubmitting || !isValid || (isCaptchaEnabled() && !captcha.hasCaptchaToken)
                  }
                  aria-describedby={isValid ? undefined : SUBMIT_HINT_ID}
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="animate-spin" />
                      Signing in...
                    </>
                  ) : (
                    'Sign In'
                  )}
                </Button>
                <SubmitHint id={SUBMIT_HINT_ID} visible={!isValid} />
                <FieldDescription className="text-center">
                  Don&apos;t have an account?{' '}
                  <Link to="/auth/signup">Create account</Link>
                </FieldDescription>
              </Field>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
