/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly SUPABASE_PROJECT_URL: string
  readonly SUPABASE_PUBLIC_API_KEY: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
