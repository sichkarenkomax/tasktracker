import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { authApi } from '../../core/auth/api'
import { useAuth } from '../../core/auth/AuthContext'
import { displayName } from '../../core/auth/types'
import { formatDateTime } from '../../core/format'
import { useMutation } from '../../core/hooks/useAsync'
import { useI18n, LOCALES } from '../../core/i18n'
import type { Locale } from '../../core/i18n'
import { getTheme, setTheme } from '../../core/theme/theme'
import type { Theme } from '../../core/theme/theme'

/**
 * The signed-in person's own settings.
 *
 * Reached by clicking their name in the header, not from "portal settings": a
 * password is not a property of the installation, and a person looking for it
 * under an administrator's menu item has to be told they are in the wrong place.
 */
export function UserProfilePage() {
  const { t, locale, setLocale } = useI18n()
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const [names, setNames] = useState({
    first_name: user?.first_name ?? '',
    last_name: user?.last_name ?? '',
  })
  const [passwords, setPasswords] = useState({ current: '', next: '' })
  const [passwordDone, setPasswordDone] = useState(false)
  const [theme, chooseTheme] = useState<Theme>(getTheme)
  const [error, setError] = useState<string | null>(null)

  const saveProfile = useMutation<{ first_name: string; last_name: string }, void>(
    async (body) => {
      await authApi.updateProfile(body)
    },
  )

  const changePassword = useMutation<
    { current_password: string; new_password: string },
    void
  >(async (body) => {
    await authApi.changePassword(body)
  })

  if (!user) return <p className="notice">{t('app.loading')}</p>

  async function submitProfile(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    const done = await saveProfile.run({
      first_name: names.first_name.trim(),
      last_name: names.last_name.trim(),
    })
    // The header shows the old name until the context refetches, so this is a
    // page reload's worth of staleness at worst - but a failed save must say so.
    if (done === null) setError(saveProfile.error)
  }

  async function submitPassword(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setPasswordDone(false)
    const done = await changePassword.run({
      current_password: passwords.current,
      new_password: passwords.next,
    })
    if (done !== null) {
      setPasswords({ current: '', next: '' })
      setPasswordDone(true)
    } else {
      setError(changePassword.error)
    }
  }

  return (
    <section className="narrow">
      <h1>{t('settings.profile')}</h1>

      <section className="panel">
        <h2>{displayName(user)}</h2>
        <form onSubmit={submitProfile}>
          <div className="fields">
            <label className="field">
              <span>{t('auth.firstName')}</span>
              <input
                maxLength={64}
                value={names.first_name}
                onChange={(event) => setNames((state) => ({ ...state, first_name: event.target.value }))}
              />
            </label>
            <label className="field">
              <span>{t('auth.lastName')}</span>
              <input
                maxLength={64}
                value={names.last_name}
                onChange={(event) => setNames((state) => ({ ...state, last_name: event.target.value }))}
              />
            </label>
          </div>
          <div className="create-form__actions">
            <button type="submit" className="button button--primary" disabled={saveProfile.pending}>
              {saveProfile.pending ? t('app.saving') : t('app.save')}
            </button>
          </div>
        </form>
        <dl className="meta">
          <dt>{t('auth.username')}</dt>
          <dd>{user.username}</dd>
          <dt>{t('auth.email')}</dt>
          <dd>{user.email}</dd>
          <dt>{t('app.createdAt')}</dt>
          <dd>{formatDateTime(user.created_at)}</dd>
          {user.is_superuser ? (
            <>
              <dt>{t('users.admin')}</dt>
              <dd>{t('app.yes')}</dd>
            </>
          ) : null}
        </dl>
      </section>

      <section className="panel">
        <h2>{t('app.language')}</h2>
        <label className="field">
          <span className="visually-hidden">{t('app.language')}</span>
          <select
            value={locale}
            onChange={(event) => setLocale(event.target.value as Locale)}
          >
            {LOCALES.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.label}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="panel">
        <h2>{t('settings.theme')}</h2>
        <label className="field">
          <span className="visually-hidden">{t('settings.theme')}</span>
          <select
            value={theme}
            onChange={(event) => {
              const next = event.target.value as Theme
              chooseTheme(next)
              setTheme(next)
            }}
          >
            <option value="gold">{t('settings.themeGold')}</option>
            <option value="blue">{t('settings.themeBlue')}</option>
          </select>
        </label>
      </section>

      <section className="panel">
        <h2>{t('auth.changePassword')}</h2>
        <form onSubmit={submitPassword}>
          <div className="fields">
            <label className="field">
              <span>{t('auth.currentPassword')}</span>
              <input
                type="password"
                autoComplete="current-password"
                required
                value={passwords.current}
                onChange={(event) =>
                  setPasswords((state) => ({ ...state, current: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>{t('auth.newPassword')}</span>
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={passwords.next}
                onChange={(event) => setPasswords((state) => ({ ...state, next: event.target.value }))}
              />
            </label>
          </div>
          <div className="create-form__actions">
            <button
              type="submit"
              className="button button--primary"
              disabled={changePassword.pending}
            >
              {changePassword.pending ? t('app.saving') : t('auth.changePassword')}
            </button>
          </div>
          {passwordDone ? <p className="notice">{t('auth.passwordChanged')}</p> : null}
        </form>
      </section>

      {error ? (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      ) : null}

      <section className="panel">
        <h2>{t('settings.session')}</h2>
        <button
          type="button"
          className="button"
          onClick={async () => {
            await signOut()
            navigate('/login')
          }}
        >
          {t('nav.signOut')}
        </button>
      </section>
    </section>
  )
}
