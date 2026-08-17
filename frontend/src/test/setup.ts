import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { toast } from 'sonner'

vi.stubEnv('SITE_KEY_CAPTCHA', 'test-site-key')

afterEach(() => {
  toast.dismiss()
  cleanup()
})
