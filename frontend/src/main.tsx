import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MockBadge } from '@/components/mock-badge'
import { Toaster } from '@/components/ui/sonner'
import { isMockMode, resetOnModeChange } from '@/lib/mockMode'
import { AppRoutes } from '@/routes/AppRoutes'
import './index.css'

/**
 * Starts the app. In a dev build with mock mode on, the mock backend is installed first, so the
 * very first API call is already answered by it. The static `import.meta.env.DEV` check lets
 * Vite drop the `mocks/` chunk from production builds entirely.
 */
async function start() {
  const mockOn = isMockMode()
  resetOnModeChange(mockOn)

  let scenario: string | null = null
  if (import.meta.env.DEV && mockOn) {
    const { startMockMode } = await import('@/mocks')
    scenario = startMockMode(window.location.search)
  }

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <AppRoutes />
      <Toaster />
      {scenario && <MockBadge scenario={scenario} />}
    </StrictMode>,
  )
}

void start()
