import fs from 'fs'
import path from 'path'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const __dirname = import.meta.dirname
const certsDir = path.resolve(__dirname, '../backend/certs')
const certPath = path.join(certsDir, 'localhost+1.pem')
const keyPath = path.join(certsDir, 'localhost+1-key.pem')
const hasHttpsCerts = fs.existsSync(certPath) && fs.existsSync(keyPath)

function redactSetCookieHeader(value: string | string[] | undefined): string[] {
  if (!value) {
    return []
  }
  const values = Array.isArray(value) ? value : [value]
  return values.map((cookie) =>
    cookie
      .replace(/^(access_token=)[^;]*/i, '$1<redacted>')
      .replace(/^(refresh_token=)[^;]*/i, '$1<redacted>'),
  )
}

function hasAccessTokenCookie(cookieHeader: string | undefined): boolean {
  if (!cookieHeader) {
    return false
  }
  return cookieHeader.split(';').some((part) => part.trim().startsWith('access_token='))
}

const authApiProxy = {
  target: process.env.AUTH_API_PROXY_TARGET ?? 'https://localhost:8000',
  changeOrigin: true,
  secure: false,
  configure(proxy) {
    proxy.on('proxyReq', (_proxyReq, req) => {
      const cookieHeader = Array.isArray(req.headers.cookie)
        ? req.headers.cookie.join('; ')
        : req.headers.cookie
      console.info('[auth-proxy] request', {
        method: req.method,
        url: req.url,
        cookieHeaderPresent: Boolean(cookieHeader),
        accessTokenCookiePresent: hasAccessTokenCookie(cookieHeader),
      })
    })
    proxy.on('proxyRes', (proxyRes, req) => {
      console.info('[auth-proxy] response', {
        method: req.method,
        url: req.url,
        status: proxyRes.statusCode,
        setCookie: redactSetCookieHeader(proxyRes.headers['set-cookie']),
      })
    })
    proxy.on('error', (err, req) => {
      console.error('[auth-proxy] error', req.method, req.url, err.message)
    })
  },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  envPrefix: ['VITE_', 'SUPABASE_', 'SITE_KEY_'],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: 'localhost',
    https: hasHttpsCerts
      ? {
          cert: fs.readFileSync(certPath),
          key: fs.readFileSync(keyPath),
        }
      : undefined,
    proxy: {
      '/api': authApiProxy,
      '/auth/refresh': authApiProxy,
    },
  },
  preview: {
    proxy: {
      '/api': authApiProxy,
      '/auth/refresh': authApiProxy,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
    testTimeout: 10000,
    server: {
      deps: {
        inline: ['@marsidev/react-turnstile'],
      },
    },
  },
})
