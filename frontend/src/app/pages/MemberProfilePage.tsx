import { Link, useParams } from 'react-router-dom'

import { useAuth } from '../../core/auth/AuthContext'
import { formatDate, formatDateTime } from '../../core/format'
import { useAsync } from '../../core/hooks/useAsync'
import { useI18n } from '../../core/i18n'
import { useOrganization } from '../../core/organizations/OrganizationContext'
import { Avatar } from '../../core/users/Avatar'
import { usersApi } from '../../core/users/api'

/**
 * Somebody else's card (stage 2.6).
 *
 * The name, department, position and avatar are always here - they are how you
 * find out who to ask, which is why every list in the product links here rather
 * than repeating the contact rules at each place a name appears.
 *
 * The contacts are the server's decision, per request, and the difference
 * between "this person hid their contacts" and "this person wrote none" is the
 * whole content of the lower half: both render as an empty area, but only one
 * of them is an answer, and telling them apart is what `contacts_visible` is
 * for. A card that guessed would either leak the hidden ones or claim that
 * somebody with a private phone number has no phone.
 */
export function MemberProfilePage() {
  const { t } = useI18n()
  const { userId } = useParams<{ userId: string }>()
  const { user } = useAuth()
  const { current: organization } = useOrganization()
  const organizationId = organization?.id ?? null

  const profile = useAsync(
    () =>
      userId && organizationId
        ? usersApi.profile(userId, organizationId)
        : Promise.resolve(null),
    [userId, organizationId],
  )

  if (profile.loading && !profile.data) return <p className="notice">{t('app.loading')}</p>

  if (profile.error) {
    return (
      <section className="narrow">
        <p className="notice notice--error" role="alert">
          {profile.error}
        </p>
        <Link className="button" to="/members">
          {t('members.title')}
        </Link>
      </section>
    )
  }

  const person = profile.data
  if (!person) return null

  const name = person.first_name || person.username
  const isMe = person.id === user?.id

  return (
    <section className="narrow">
      <header className="page-header">
        <Link className="page-header__back" to="/members">
          <span>{t('app.back')}</span>
        </Link>
      </header>

      <section className="panel">
        <div className="profile-head">
          <Avatar src={person.avatar_url} name={name} size="lg" />
          <div className="profile-head__identity">
            <h1>
              {name}
              {isMe ? <span className="muted"> ({t('members.you')})</span> : null}
            </h1>
            <p className="muted">
              {person.position_title ?? person.department_name ?? `@${person.username}`}
            </p>
            {person.department_name && person.position_title ? (
              <p className="muted">{person.department_name}</p>
            ) : null}
          </div>
        </div>

        <dl className="meta">
          <dt>{t('auth.username')}</dt>
          <dd>{person.username}</dd>
          {person.role ? (
            <>
              <dt>{t('members.role')}</dt>
              <dd>{t(`role.${person.role}` as 'role.member')}</dd>
            </>
          ) : null}
          {person.last_login_at ? (
            <>
              <dt>{t('profile.lastSeen')}</dt>
              <dd>{formatDateTime(person.last_login_at)}</dd>
            </>
          ) : null}
        </dl>
      </section>

      <section className="panel">
        <h2>{t('profile.contacts')}</h2>

        {person.contacts_visible ? (
          <>
            <dl className="meta">
              {person.email ? (
                <>
                  <dt>{t('auth.email')}</dt>
                  <dd>{person.email}</dd>
                </>
              ) : null}
              {person.birthday ? (
                <>
                  <dt>{t('profile.birthday')}</dt>
                  <dd>{formatDate(person.birthday)}</dd>
                </>
              ) : null}
            </dl>

            {person.phones.length > 0 ? (
              <ul className="org__list">
                {person.phones.map((phone) => (
                  <li key={phone.id}>
                    <a href={`tel:${phone.number.replace(/[^\d+]/g, '')}`}>{phone.number}</a>
                    {phone.comment ? <span className="muted"> — {phone.comment}</span> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">{t('profile.noPhones')}</p>
            )}

            {!person.email && !person.birthday && person.phones.length === 0 ? (
              <p className="muted">{t('profile.noContacts')}</p>
            ) : null}
          </>
        ) : (
          // The one case worth saying out loud: an empty "contacts" block that is
          // a decision rather than an omission.
          <p className="muted">{t('profile.contactsHidden')}</p>
        )}
      </section>

      <section className="panel">
        <h2>{t('profile.messageTitle')}</h2>
        {/* No button yet: the roadmap asks for this action to be hidden until
            chat exists (stage 8), and a disabled control that looks like a
            feature nobody finished is worse than a sentence saying what is
            coming. The heading stays, so the place the action will take is
            visible in the shape of the screen. */}
        <p className="muted">{t('profile.messageLater')}</p>
      </section>

      {isMe ? (
        <p className="muted">
          <Link to="/users/me">{t('profile.editOwn')}</Link>
        </p>
      ) : null}
    </section>
  )
}