import * as matchers from '@testing-library/jest-dom/matchers'
import { cleanup } from '@testing-library/react'
import { toast } from 'sonner'

expect.extend(matchers)

vi.stubEnv('SITE_KEY_CAPTCHA', 'test-site-key')

vi.mock('@marsidev/react-turnstile', async () => {
  const { MockTurnstile } = await import('@/test/mocks/turnstile')
  return { Turnstile: MockTurnstile }
})

afterEach(() => {
  localStorage.clear()
  toast.dismiss()
  cleanup()
})
