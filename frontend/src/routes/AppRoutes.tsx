import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { SignupPage } from '@/pages/SignupPage'

/** Application route definitions. */
export function AppRoutes() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/" element={<Navigate to="/signup" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
