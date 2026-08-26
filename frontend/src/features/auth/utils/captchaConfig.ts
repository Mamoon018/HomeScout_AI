/** Whether Turnstile captcha is required for login and signup. */
export function isCaptchaEnabled(): boolean {
  const explicit = import.meta.env.VITE_CAPTCHA_ENABLED

  if (explicit === 'true') {
    return true
  }
  if (explicit === 'false') {
    return false
  }

  return import.meta.env.PROD
}

/** Returns the Cloudflare Turnstile site key from environment variables. */
export function getCaptchaSiteKey(): string {
  const siteKey = import.meta.env.SITE_KEY_CAPTCHA

  if (!siteKey) {
    throw new Error(
      'SITE_KEY_CAPTCHA is missing. Add it to frontend/.env to enable captcha.',
    )
  }

  return siteKey
}
