import { AuthLayout } from '@/components/auth-layout'
import { LoginForm } from '@/components/login-form'

/** Login page using the shared auth shell. */
export function LoginPage() {
  return <AuthLayout centerForm formContent={<LoginForm />} />
}
