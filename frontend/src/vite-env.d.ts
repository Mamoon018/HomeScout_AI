/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly SUPABASE_PROJECT_URL: string
  readonly SUPABASE_PUBLIC_API_KEY: string
  readonly SITE_KEY_CAPTCHA: string
  readonly VITE_CAPTCHA_ENABLED?: string
  /** "true" in a dev build answers backend calls from the dev mock (src/mocks). Ignored in production. */
  readonly VITE_USE_MOCK_API?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
