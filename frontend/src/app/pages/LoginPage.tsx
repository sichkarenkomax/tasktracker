import { useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'

import { ApiError } from '../../core/api/client'
import { useAuth } from '../../core/auth/AuthContext'
import { useI18n } from '../../core/i18n'

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
  const { t } = useI18n()
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
      return t('auth.invalidCredentials')
    }
    if (cause instanceof ApiError && cause.isValidation) {
      return cause.detail
    }
    return cause instanceof Error ? cause.message : t('error.generic')
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
      <h1>{mode === 'signin' ? t('auth.signInTitle') : t('auth.signUp')}</h1>
      <p className="muted">{t('auth.intro')}</p>

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
          {t('auth.signIn')}
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
          {t('auth.signUp')}
        </button>
      </div>

      <form className="auth__form" onSubmit={submit}>
        {mode === 'signin' ? (
          <label>
            <span>{t('auth.emailOrUsername')}</span>
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
              <span>{t('auth.email')}</span>
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
              <span>{t('auth.username')}</span>
              <input
                autoComplete="username"
                required
                minLength={3}
                pattern="[a-zA-Z0-9_.\-]+"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
              <small className="muted">{t('auth.usernameHint')}</small>
            </label>
            <label>
              <span>{t('auth.firstName')}</span>
              <input
                autoComplete="given-name"
                value={firstName}
                onChange={(event) => setFirstName(event.target.value)}
              />
            </label>
          </>
        )}

        <label>
          <span>{t('auth.password')}</span>
          <input
            type="password"
            autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
            required
            minLength={mode === 'signup' ? 8 : 1}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          {mode === 'signup' ? <small className="muted">{t('auth.passwordHint')}</small> : null}
        </label>

        {error ? (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        ) : null}

        <button type="submit" className="button button--primary" disabled={pending}>
          {pending
            ? t('app.loading')
            : mode === 'signin'
              ? t('auth.signIn')
              : t('auth.createAccount')}
        </button>
      </form>

      <p className="muted">
        <Link to="/">{t('app.goHome')}</Link>
      </p>
    </section>
  )
}
