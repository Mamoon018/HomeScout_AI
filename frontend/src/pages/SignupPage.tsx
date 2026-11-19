import { AuthLayout } from '@/features/auth/components/auth-layout'
import { SignupForm } from '@/features/auth/components/signup-form'

/** Signup page: same Olive Glass shell as sign-in, with the signup form level with the tagline. */
export function SignupPage() {
  return <AuthLayout theme="olive" centerForm formPlacement="tagline" formContent={<SignupForm />} />
}
