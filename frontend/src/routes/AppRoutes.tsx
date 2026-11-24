import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { HomePage } from '@/pages/HomePage'
import { LoginPage } from '@/pages/LoginPage'
import { PlacesMetricsPage } from '@/pages/PlacesMetricsPage'
import { ProximityPage } from '@/pages/ProximityPage'
import { SignupPage } from '@/pages/SignupPage'

/**
 * Application route definitions: URL → page only. Lost-session handling lives in
 * features/auth/hooks/useUnauthenticatedRedirect, which each signed-in page calls.
 */
export function AppRoutes() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/auth/login" element={<LoginPage />} />
        <Route path="/auth/signup" element={<SignupPage />} />
        <Route path="/signup" element={<Navigate to="/auth/signup" replace />} />
        <Route path="/home" element={<HomePage />} />
        <Route path="/proximity_info" element={<ProximityPage />} />
        <Route path="/places_metrics" element={<PlacesMetricsPage />} />
        <Route path="/" element={<Navigate to="/auth/login" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
