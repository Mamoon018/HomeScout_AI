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
