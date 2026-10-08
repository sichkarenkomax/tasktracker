import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { authApi } from '../../core/auth/api'
import { useAuth } from '../../core/auth/AuthContext'
import { displayName } from '../../core/auth/types'
import { filesApi } from '../../core/files/api'
import { prepareAvatar } from '../../core/files/prepare'
import { formatDateTime } from '../../core/format'
import { useMutation } from '../../core/hooks/useAsync'
import { useI18n } from '../../core/i18n'
import { useOrganization } from '../../core/organizations/OrganizationContext'
import { Avatar } from '../../core/users/Avatar'

/**
 * The signed-in person's own account.
 *
 * Reached by clicking their name in the header, not from "portal settings": a
 * password is not a property of the installation, and a person looking for it
 * under an administrator's menu item has to be told they are in the wrong place.
 *
 * Preferences (language, theme) live on their own screen, `/preferences` - see
 * `PreferencesPage` for why the two were separated.
 */
export function UserProfilePage() {
  const { t } = useI18n()
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const [names, setNames] = useState({
    first_name: user?.first_name ?? '',
    last_name: user?.last_name ?? '',
  })
  const [passwords, setPasswords] = useState({ current: '', next: '' })
  const [passwordDone, setPasswordDone] = useState(false)
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
          <AvatarUpload />
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

/**
 * The picture (stage 2.3).
 *
 * Nothing here asks the person to crop anything: `prepareAvatar` centres and
 * squares the image in the browser, and the server is sent one small square. It is
 * also the first thing in the product to go through the files API, so the limits
 * and the quota the portal declares are read *before* the upload rather than
 * discovered after it - the panel says how much room is left and refuses a file
 * the portal would refuse anyway.
 */
function AvatarUpload() {
  const { t } = useI18n()
  const { user, refresh } = useAuth()
  const { current: organization } = useOrganization()
  const organizationId = organization?.id ?? null
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const upload = useMutation<File, void>(async (file) => {
    if (!organizationId || !user) throw new Error(t('error.generic'))
    const stored = await filesApi.upload(organizationId, file)
    await authApi.updateProfile({
      avatar_url: filesApi.downloadUrl(stored.id, organizationId),
    })
    // The header and this page both read the signed-in person from the auth
    // context, so without this the new picture is stored and still not shown.
    await refresh()
  })

  const limits = useMutation<void, { remaining_bytes: number | null }>(async () => {
    if (!organizationId) throw new Error(t('error.generic'))
    const room = await filesApi.limits(organizationId)
    return { remaining_bytes: room.remaining_bytes }
  })

  if (!user) return null

  async function onPick(event: React.ChangeEvent<HTMLInputElement>) {
    const picked = event.target.files?.[0]
    // Clear the input so choosing the same file twice in a row still fires.
    event.target.value = ''
    if (!picked || !organizationId) return

    setMessage(null)
    setBusy(true)
    try {
      const room = await limits.run()
      if (room === null) {
        setMessage(limits.error ?? t('error.generic'))
        return
      }
      if (room.remaining_bytes === 0) {
        setMessage(t('profile.avatarNoRoom'))
        return
      }
      // Cropped and shrunk here, so the portal never spends a byte of CPU on an
      // image it does not need to understand.
      const prepared = await prepareAvatar(picked, 512)
      if (room.remaining_bytes !== null && prepared.size > room.remaining_bytes) {
        setMessage(t('profile.avatarTooBig'))
        return
      }
      const done = await upload.run(prepared)
      if (done === null) setMessage(upload.error)
    } catch {
      setMessage(t('error.generic'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="avatar-upload">
      <Avatar src={user.avatar_url} name={displayName(user)} size="lg" />
      <div className="avatar-upload__controls">
        <input
          ref={inputRef}
          type="file"
          accept="image/png,image/jpeg,image/gif,image/webp"
          className="visually-hidden"
          onChange={(event) => void onPick(event)}
        />
        <button
          type="button"
          className="button"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {busy ? t('app.saving') : t('profile.avatarChoose')}
        </button>
        <p className="muted">{t('profile.avatarHint')}</p>
        {message ? (
          <p className="field__error" role="alert">
            {message}
          </p>
        ) : null}
      </div>
    </div>
  )
}
