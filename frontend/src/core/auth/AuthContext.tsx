import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { ApiError } from '../api/client'
import { authApi } from './api'
import type { SessionUser } from './types'

/**
 * The session, as the SPA knows it.
 *
 * There is no token in here on purpose. The API issues an httpOnly cookie, so the
 * browser attaches the session to every request and no script - ours or an
 * attacker's - can read it. What React keeps is only the user record, used to
 * render the header.
 *
 * `status` exists because "not signed in" and "we have not asked yet" look
 * identical while the first request is in flight, and routing on that difference
 * is what produces the classic flash of the login page on every reload.
 */
type Status = 'loading' | 'authenticated' | 'anonymous' | 'unreachable'

interface AuthState {
  status: Status
  user: SessionUser | null
  /** Why the session could not be checked, when it could not be checked. */
  error: string | null
  signIn: (login: string, password: string) => Promise<void>
  signUp: (input: {
    email: string
    username: string
    password: string
    first_name?: string
  }) => Promise<void>
  signOut: () => Promise<void>
  /** Re-read the person, after something else changed their profile. */
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [user, setUser] = useState<SessionUser | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    authApi
      .me()
      .then((profile) => {
        if (cancelled) return
        setUser(profile)
        setStatus('authenticated')
      })
      .catch((cause: unknown) => {
        if (cancelled) return
        if (cause instanceof ApiError && cause.isUnauthorized) {
          setStatus('anonymous')
          return
        }
        // A backend that is down must not be mistaken for a signed-out visitor:
        // sending them to the login form turns one clear message into a puzzle.
        setError(cause instanceof Error ? cause.message : 'Cannot reach the server')
        setStatus('unreachable')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const signIn = useCallback(async (login: string, password: string) => {
    // The login response carries the summary shape - no `is_superuser`, no
    // `last_login_at` - so the profile is fetched as well. Registering and signing
    // in then leave the session record in exactly the same state.
    await authApi.login({ login, password })
    setUser(await authApi.me())
    setError(null)
    setStatus('authenticated')
  }, [])

  const signUp = useCallback(
    async (input: { email: string; username: string; password: string; first_name?: string }) => {
      await authApi.register(input)
      setUser(await authApi.me())
      setError(null)
      setStatus('authenticated')
    },
    [],
  )

  const signOut = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      // The cookie is cleared server-side; drop the local copy either way, so a
      // failed request cannot leave the header showing a signed-in user.
      setUser(null)
      setStatus('anonymous')
    }
  }, [])

  /**
   * Re-read the signed-in person.
   *
   * Needed after something elsewhere changed their profile - an avatar upload,
   * a name typed in another tab - because the header and the profile page both
   * read this copy, and a stale one is how a saved change appears not to have
   * happened.
   */
  const refresh = useCallback(async () => {
    try {
      setUser(await authApi.me())
    } catch {
      // A refresh is best-effort: the session is unchanged either way, and a
      // failed read must not sign anybody out.
    }
  }, [])

  const value = useMemo<AuthState>(
    () => ({ status, user, error, signIn, signUp, signOut, refresh }),
    [status, user, error, signIn, signUp, signOut, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (context === null) {
    throw new Error('useAuth must be used inside <AuthProvider>')
  }
  return context
}
