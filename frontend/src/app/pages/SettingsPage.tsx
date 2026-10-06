import { useState } from 'react'

import { formatDateTime } from '../../core/format'
import { useAsync, useMutation } from '../../core/hooks/useAsync'
import { authApi } from '../../core/auth/api'
import { useAuth } from '../../core/auth/AuthContext'
import { displayName } from '../../core/auth/types'
import { organizationsApi } from '../../core/organizations/api'
import { useOrganization } from '../../core/organizations/OrganizationContext'

/**
 * Profile and organization settings (the `/settings` route in §29).
 *
 * Settings are shown as the effective values the API returns rather than as an
 * editable form for every key: they are free-form JSON today, and a form
 * generated from that would need rebuilding every time a setting is added.
 */
export function SettingsPage() {
  const { user, signOut } = useAuth()
  const { current: organization } = useOrganization()
  const organizationId = organization?.id ?? null

  const settings = useAsync(
    () =>
      organizationId
        ? organizationsApi.settings(organizationId)
        : Promise.resolve({ values: {}, updated_at: null }),
    [organizationId],
  )

  const [passwords, setPasswords] = useState({ current: '', next: '' })
  const changePassword = useMutation<{ current_password: string; new_password: string }, void>(
    async (body) => {
      await authApi.changePassword(body)
    },
  )

  if (!user) return <p className="notice">Loading...</p>

  async function submitPassword(event: React.FormEvent) {
    event.preventDefault()
    const done = await changePassword.run({
      current_password: passwords.current,
      new_password: passwords.next,
    })
    if (done !== null) setPasswords({ current: '', next: '' })
  }

  return (
    <section>
      <h1>Settings</h1>

      <section className="panel">
        <h2>Profile</h2>
        <dl className="meta">
          <dt>Name</dt>
          <dd>{displayName(user)}</dd>
          <dt>Username</dt>
          <dd>{user.username}</dd>
          <dt>Email</dt>
          <dd>{user.email}</dd>
          <dt>Member since</dt>
          <dd>{formatDateTime(user.created_at)}</dd>
        </dl>
      </section>

      <section className="panel">
        <h2>Password</h2>
        <form className="auth__form" onSubmit={submitPassword}>
          <label>
            <span>Current password</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={passwords.current}
              onChange={(event) => setPasswords((state) => ({ ...state, current: event.target.value }))}
            />
          </label>
          <label>
            <span>New password</span>
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={passwords.next}
              onChange={(event) => setPasswords((state) => ({ ...state, next: event.target.value }))}
            />
          </label>
          <button type="submit" className="button" disabled={changePassword.pending}>
            {changePassword.pending ? 'Saving...' : 'Change password'}
          </button>
          {changePassword.error ? (
            <p className="notice notice--error" role="alert">
              {changePassword.error}
            </p>
          ) : null}
        </form>
      </section>

      {organization ? (
        <section className="panel">
          <h2>Organization: {organization.name}</h2>
          {settings.error ? (
            <p className="notice notice--error">{settings.error}</p>
          ) : null}
          <p className="muted">
            Updated {settings.data?.updated_at ? formatDateTime(settings.data.updated_at) : 'never'}
          </p>
          <dl className="meta">
            {Object.entries(settings.data?.values ?? {}).map(([key, value]) => (
              <div key={key} className="meta__pair">
                <dt>{key}</dt>
                <dd>{String(value)}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      <section className="panel">
        <h2>Session</h2>
        <button type="button" className="button" onClick={() => void signOut()}>
          Sign out
        </button>
      </section>
    </section>
  )
}
