import { AuthLayout } from '@/components/auth-layout'
import { SignupForm } from '@/components/signup-form'

/** Signup page with shared auth shell and signup form. */
export function SignupPage() {
  return <AuthLayout formContent={<SignupForm />} />
}
