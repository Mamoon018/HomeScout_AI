/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly SUPABASE_PROJECT_URL: string
  readonly SUPABASE_PUBLIC_API_KEY: string
  readonly SITE_KEY_CAPTCHA: string
  readonly VITE_CAPTCHA_ENABLED?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
