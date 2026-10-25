import { createBrowserClient } from "@supabase/ssr";

// Browser client for the configured Supabase project: the Vite port of the
// supabase-client-nextjs block (Vite exposes NEXT_PUBLIC_* through envPrefix).
// The block's server and middleware files need a Next.js server runtime and do
// not apply to this single-page application. Only the project URL and the
// publishable key are read here; this module sends no patient data anywhere.

export function isSupabaseConfigured(): boolean {
  return Boolean(import.meta.env.NEXT_PUBLIC_SUPABASE_URL && import.meta.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY);
}

export function createClient() {
  const url = import.meta.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = import.meta.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) {
    throw new Error("Supabase is not configured: set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY in .env.local.");
  }
  return createBrowserClient(url, key);
}
