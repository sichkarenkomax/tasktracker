import { Navigate, useLocation } from 'react-router-dom'
import type { ReactElement } from 'react'

import { useAuth } from './AuthContext'

/**
 * Gate for every page that needs a session.
 *
 * Waiting for `loading` to finish before deciding is the whole point: redirecting
 * while the question is still open would bounce a signed-in user to the login
 * form on every full page load.
 */
export function RequireAuth({ children }: { children: ReactElement }) {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return <p className="notice">Checking your session...</p>
  }

  if (status === 'unreachable') {
    return (
      <p className="notice notice--error" role="alert">
        The backend is unreachable. Start it with <code>docker compose up -d</code> and reload.
      </p>
    )
  }

  if (status === 'anonymous') {
    // `from` lets the login page send the visitor back where they were headed.
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }

  return children
}
