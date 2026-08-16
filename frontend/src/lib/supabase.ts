// Browser-only Supabase client. Reads SUPABASE_PROJECT_URL and SUPABASE_PUBLIC_API_KEY from .env.
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.SUPABASE_PROJECT_URL
const supabaseAnonKey = import.meta.env.SUPABASE_PUBLIC_API_KEY

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
