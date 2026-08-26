import { useCallback, useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { getUserWelcome } from '@/features/auth/api/authApi'
import { welcomeMessageFromResponse } from '@/features/auth/utils/welcomeMessage'
import { HomePage } from '@/pages/HomePage'
import { LoginPage } from '@/pages/LoginPage'
import { SignupPage } from '@/pages/SignupPage'

function HomeRoute() {
  const navigate = useNavigate()
  const [message, setMessage] = useState<string | null>(null)
  const onUnauthenticated = useCallback(() => {
    navigate('/auth/login', { replace: true })
  }, [navigate])

  useEffect(() => {
    let cancelled = false

    getUserWelcome()
      .then((result) => {
        if (cancelled) {
          return
        }
        const nextMessage = welcomeMessageFromResponse(result, onUnauthenticated)
        if (nextMessage) {
          setMessage(nextMessage)
        }
      })
      .catch(() => {
        /* Leave the homepage empty; 401 already redirects via onUnauthenticated. */
      })

    return () => {
      cancelled = true
    }
  }, [onUnauthenticated])

  return <HomePage message={message} />
}

/** Application route definitions. */
export function AppRoutes() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/auth/login" element={<LoginPage />} />
        <Route path="/auth/signup" element={<SignupPage />} />
        <Route path="/signup" element={<Navigate to="/auth/signup" replace />} />
        <Route path="/home" element={<HomeRoute />} />
        <Route path="/" element={<Navigate to="/auth/login" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
