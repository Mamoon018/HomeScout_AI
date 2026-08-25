import { useState } from 'react'
import { Link } from 'react-router-dom'
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'
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
  FieldError,
  FieldGroup,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useLogin } from '@/features/auth/hooks/useLogin'
import { useSignupCaptcha } from '@/features/auth/hooks/useSignupCaptcha'
import {
  INVALID_INPUT_MESSAGE,
  loginSchema,
  type LoginFormData,
} from '@/features/auth/utils/loginSchema'
import { SignupCaptcha } from '@/components/signup-captcha'

export function LoginForm({
  className,
  ...props
}: React.ComponentProps<'div'>) {
  const captcha = useSignupCaptcha()
  const { isSubmitting, submitLogin } = useLogin(captcha)
  const [showPassword, setShowPassword] = useState(false)
  const passwordInputType = showPassword ? 'text' : 'password'

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    mode: 'onSubmit',
    defaultValues: {
      email: '',
      password: '',
    },
  })

  return (
    <div className={cn('flex flex-col gap-6', className)} {...props}>
      <Card className="border-border/60 bg-card">
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
                  {...register('email')}
                />
                <FieldError>
                  {errors.email ? INVALID_INPUT_MESSAGE : null}
                </FieldError>
              </Field>
              <Field data-invalid={!!errors.password}>
                <FieldLabel htmlFor="login-password">Password</FieldLabel>
                <Input
                  id="login-password"
                  type={passwordInputType}
                  autoComplete="current-password"
                  disabled={isSubmitting}
                  aria-invalid={!!errors.password}
                  {...register('password')}
                />
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
                    className="text-sm font-normal text-muted-foreground"
                  >
                    Show password
                  </Label>
                </div>
                <FieldError>
                  {errors.password ? INVALID_INPUT_MESSAGE : null}
                </FieldError>
              </Field>
              <SignupCaptcha
                disabled={isSubmitting}
                captcha={captcha}
                description="Complete the captcha challenge to enable sign in."
              />
              <Field>
                <Button
                  type="submit"
                  className="w-full"
                  disabled={isSubmitting || !captcha.hasCaptchaToken}
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
