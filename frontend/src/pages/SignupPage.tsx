import { AuthLayout } from '@/features/auth/components/auth-layout'
import { SignupForm } from '@/features/auth/components/signup-form'

/** Signup page with shared auth shell and signup form. */
export function SignupPage() {
  return <AuthLayout formContent={<SignupForm />} />
}
