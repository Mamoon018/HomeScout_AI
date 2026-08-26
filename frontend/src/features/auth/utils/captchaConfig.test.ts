import { isCaptchaEnabled } from '@/features/auth/utils/captchaConfig'

describe('isCaptchaEnabled', () => {
  const originalProd = import.meta.env.PROD
  const originalOverride = import.meta.env.VITE_CAPTCHA_ENABLED

  afterEach(() => {
    import.meta.env.PROD = originalProd
    import.meta.env.VITE_CAPTCHA_ENABLED = originalOverride
  })

  it('returns false in non-production when override is unset', () => {
    import.meta.env.PROD = false
    import.meta.env.VITE_CAPTCHA_ENABLED = undefined

    expect(isCaptchaEnabled()).toBe(false)
  })

  it('returns true in production when override is unset', () => {
    import.meta.env.PROD = true
    import.meta.env.VITE_CAPTCHA_ENABLED = undefined

    expect(isCaptchaEnabled()).toBe(true)
  })

  it('honors VITE_CAPTCHA_ENABLED=true override', () => {
    import.meta.env.PROD = false
    import.meta.env.VITE_CAPTCHA_ENABLED = 'true'

    expect(isCaptchaEnabled()).toBe(true)
  })

  it('honors VITE_CAPTCHA_ENABLED=false override', () => {
    import.meta.env.PROD = true
    import.meta.env.VITE_CAPTCHA_ENABLED = 'false'

    expect(isCaptchaEnabled()).toBe(false)
  })
})
