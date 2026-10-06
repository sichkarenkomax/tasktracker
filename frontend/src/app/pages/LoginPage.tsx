import { useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'

import { ApiError } from '../../core/api/client'
import { useAuth } from '../../core/auth/AuthContext'

/**
 * Sign in and sign up on one screen.
 *
 * Two tabs rather than two routes: the decision "am I creating an account or
 * using one?" is made before anything is typed, and a person who picked the wrong
 * tab should not have to retype a password to switch.
 */
type Mode = 'signin' | 'signup'

interface LocationState {
  from?: string
}

export function LoginPage() {
  const { status, signIn, signUp } = useAuth()
  const location = useLocation()
  const [mode, setMode] = useState<Mode>('signin')
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [firstName, setFirstName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  if (status === 'authenticated') {
    const from = (location.state as LocationState | null)?.from
    return <Navigate to={from && from !== '/login' ? from : '/projects'} replace />
  }

  function readable(cause: unknown): string {
    if (cause instanceof ApiError && cause.code === 'invalid_credentials') {
      return 'That email, username or password is not right.'
    }
    if (cause instanceof ApiError && cause.isValidation) {
      return cause.detail
    }
    return cause instanceof Error ? cause.message : 'Sign in failed'
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      if (mode === 'signin') {
        await signIn(login.trim(), password)
      } else {
        await signUp({
          email: email.trim(),
          username: username.trim(),
          password,
          ...(firstName.trim() ? { first_name: firstName.trim() } : {}),
        })
      }
    } catch (cause: unknown) {
      setError(readable(cause))
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="auth">
      <h1>{mode === 'signin' ? 'Sign in' : 'Create an account'}</h1>
      <p className="muted">
        TaskTracker is self-hosted: the first account becomes the owner of its own organization.
      </p>

      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'signin'}
          className={mode === 'signin' ? 'tabs__tab tabs__tab--active' : 'tabs__tab'}
          onClick={() => {
            setMode('signin')
            setError(null)
          }}
        >
          Sign in
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'signup'}
          className={mode === 'signup' ? 'tabs__tab tabs__tab--active' : 'tabs__tab'}
          onClick={() => {
            setMode('signup')
            setError(null)
          }}
        >
          Sign up
        </button>
      </div>

      <form className="auth__form" onSubmit={submit}>
        {mode === 'signin' ? (
          <label>
            <span>Email or username</span>
            <input
              autoFocus
              autoComplete="username"
              required
              value={login}
              onChange={(event) => setLogin(event.target.value)}
            />
          </label>
        ) : (
          <>
            <label>
              <span>Email</span>
              <input
                autoFocus
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label>
              <span>Username</span>
              <input
                autoComplete="username"
                required
                minLength={3}
                pattern="[a-zA-Z0-9_.\-]+"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
              <small className="muted">Letters, digits, dot, dash and underscore.</small>
            </label>
            <label>
              <span>First name</span>
              <input
                autoComplete="given-name"
                value={firstName}
                onChange={(event) => setFirstName(event.target.value)}
              />
            </label>
          </>
        )}

        <label>
          <span>Password</span>
          <input
            type="password"
            autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
            required
            minLength={mode === 'signup' ? 8 : 1}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          {mode === 'signup' ? <small className="muted">At least 8 characters.</small> : null}
        </label>

        {error ? (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        ) : null}

        <button type="submit" className="button button--primary" disabled={pending}>
          {pending ? 'Please wait...' : mode === 'signin' ? 'Sign in' : 'Create account'}
        </button>
      </form>

      <p className="muted">
        <Link to="/">Back to the start</Link>
      </p>
    </section>
  )
}
