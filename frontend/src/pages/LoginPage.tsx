import { AuthLayout } from '@/features/auth/components/auth-layout'
import { LoginForm } from '@/features/auth/components/login-form'

/** Login page using the shared auth shell. */
export function LoginPage() {
  return <AuthLayout theme="olive" centerForm formContent={<LoginForm />} />
}
