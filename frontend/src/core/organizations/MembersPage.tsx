import { useState } from 'react'
import { Link } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { useAsync, useMutation } from '../hooks/useAsync'
import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n'
import { Icon } from '../layout/Icon'
import { Listbox } from '../ui/Listbox'
import { Avatar } from '../users/Avatar'
import { usersApi } from '../users/api'
import { organizationsApi } from './api'
import type { Member, OrganizationRole } from './api'
import { useOrganizationId } from './OrganizationContext'
import { RequiresOrganization } from './RequiresOrganization'

/**
 * Who is in this organization, and what they may do.
 *
 * The four roles are fixed by the backend matrix (section 25), so this screen
 * chooses between them rather than inventing permissions of its own. What it does
 * decide is the ceiling: a person may only hand out a role strictly below their
 * own, and never touch somebody at or above their level. That mirrors the rule
 * the API enforces, so the impossible options are not offered in the first place.
 */

/** Highest privilege first; the index in this list *is* the rank. */
const ROLE_ORDER: OrganizationRole[] = ['owner', 'admin', 'member', 'viewer']

const ROLE_HINTS: Record<OrganizationRole, TranslationKey> = {
  owner: 'role.ownerHint',
  admin: 'role.adminHint',
  member: 'role.memberHint',
  viewer: 'role.viewerHint',
}

function roleLabel(role: OrganizationRole): TranslationKey {
  return `role.${role}` as TranslationKey
}

export function MembersPage() {
  return (
    <RequiresOrganization>
      <Members />
    </RequiresOrganization>
  )
}

function Members() {
  const { t } = useI18n()
  const { user } = useAuth()
  const organizationId = useOrganizationId()
  const [adding, setAdding] = useState(false)

  const roster = useAsync(
    () => (organizationId ? organizationsApi.members(organizationId) : Promise.resolve([])),
    [organizationId],
  )

  if (organizationId === null) return null

  const members = roster.data ?? []
  const myRole = members.find((member) => member.user_id === user?.id)?.role
  // With no membership of our own we are not in the list at all, which can only
  // mean the request was refused or the account is new; treat it as no rights.
  const myRank = myRole ? ROLE_ORDER.indexOf(myRole) : -1
  const mayInvite = myRank >= 0 && myRank < ROLE_ORDER.indexOf('admin')

  return (
    <section>
      <header className="page-header">
        <h1>{t('members.title')}</h1>
        {mayInvite ? (
          <button
            type="button"
            className="button button--primary"
            onClick={() => setAdding((open) => !open)}
          >
            <Icon name="plus" size={15} />
            {t('members.add')}
          </button>
        ) : null}
      </header>

      {adding ? (
        <AddMember
          organizationId={organizationId}
          onDone={() => {
            setAdding(false)
            roster.reload()
          }}
        />
      ) : null}

      {roster.error ? (
        <p className="notice notice--error" role="alert">
          {roster.error}
        </p>
      ) : null}
      {roster.loading && !roster.data ? <p className="notice">{t('app.loading')}</p> : null}

      {members.length === 0 && !roster.loading ? (
        <p className="notice">{t('members.empty')}</p>
      ) : null}

      <ul className="member-list">
        {members.map((member) => (
          <MemberRow
            key={member.user_id}
            member={member}
            organizationId={organizationId}
            myRank={myRank}
            isMe={member.user_id === user?.id}
            onChanged={roster.reload}
          />
        ))}
      </ul>
    </section>
  )
}

function MemberRow({
  member,
  organizationId,
  myRank,
  isMe,
  onChanged,
}: {
  member: Member
  organizationId: string
  myRank: number
  isMe: boolean
  onChanged: () => void
}) {
  const { t } = useI18n()
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [editingEmail, setEditingEmail] = useState(false)

  const changeRole = useMutation<OrganizationRole, void>(async (role) => {
    await organizationsApi.setMemberRole(organizationId, member.user_id, role)
  })

  const remove = useMutation<void, void>(async () => {
    await organizationsApi.removeMember(organizationId, member.user_id)
  })

  const theirRank = ROLE_ORDER.indexOf(member.role)
  // Strictly below: an admin cannot touch another admin, and nobody can demote
  // themselves, which is also how the API refuses it.
  const mayManage = myRank !== -1 && theirRank > myRank
  const roleOptions = ROLE_ORDER.slice(0, Math.max(0, myRank))

  return (
    <li className="member">
      <Avatar
        src={member.avatar_url}
        name={member.first_name || member.username}
        size="sm"
      />

      <div className="member__identity">
        {/* The name is a link to the card behind it (stage 2.6): the list answers
            "who is in this organization", and the profile answers "who is this
            and how do I reach them". */}
        <Link to={`/users/${member.user_id}`}>
          <strong>
            {member.first_name || member.username}
            {isMe ? <span className="muted"> ({t('members.you')})</span> : null}
          </strong>
        </Link>
        <span className="muted">
          {member.position_title ?? member.email}
        </span>
      </div>

      {mayManage ? (
        <label className="member__role">
          <span className="visually-hidden">{t('members.role')}</span>
          <Listbox<OrganizationRole>
            value={member.role}
            options={roleOptions.map((role) => ({
              value: role,
              label: t(roleLabel(role)),
              hint: t(ROLE_HINTS[role]),
            }))}
            disabled={changeRole.pending}
            onChange={async (next) => {
              if (next === null) return
              setError(null)
              const done = await changeRole.run(next)
              if (done !== null) onChanged()
              else setError(changeRole.error)
            }}
          />
        </label>
      ) : (
        <span className="badge" title={t(ROLE_HINTS[member.role])}>
          {t(roleLabel(member.role))}
        </span>
      )}

      {mayManage ? (
        confirming ? (
          <span className="member__confirm">
            <button
              type="button"
              className="button button--danger"
              disabled={remove.pending}
              onClick={async () => {
                const done = await remove.run()
                if (done !== null) {
                  setConfirming(false)
                  onChanged()
                } else {
                  setError(remove.error)
                }
              }}
            >
              {t('members.removeConfirm', { name: member.first_name || member.username })}
            </button>
            <button type="button" className="link" onClick={() => setConfirming(false)}>
              {t('app.cancel')}
            </button>
          </span>
        ) : (
          <>
            {/* Stage 2.7: an administrator fixes somebody's address. The button
                is here and nowhere else, because "may manage" is the same ceiling
                the API enforces - offering it to somebody who would be refused
                would be a control that only teaches the difference between 403s. */}
            <button type="button" className="link" onClick={() => setEditingEmail(true)}>
              {t('members.changeEmail')}
            </button>
            <button type="button" className="link" onClick={() => setConfirming(true)}>
              {t('members.remove')}
            </button>
          </>
        )
      ) : null}

      {editingEmail ? (
        <EmailEditor
          member={member}
          organizationId={organizationId}
          onDone={() => {
            setEditingEmail(false)
            onChanged()
          }}
          onCancel={() => setEditingEmail(false)}
        />
      ) : null}

      {error ? (
        <span className="field__error" role="alert">
          {error}
        </span>
      ) : null}
    </li>
  )
}

/**
 * The administrator's editor for somebody else's address (stage 2.7).
 *
 * Two things it deliberately does not do: no confirmation round trip, because
 * nobody sends mail in v1 and the activity feed is the record; and no "send a
 * letter to the new address" button, because there is no letter. What it does
 * do is say that the change is visible in the feed - an address that moves
 * silently is an address a person discovers by failing to get into their own
 * account.
 */
function EmailEditor({
  member,
  organizationId,
  onDone,
  onCancel,
}: {
  member: Member
  organizationId: string
  onDone: () => void
  onCancel: () => void
}) {
  const { t } = useI18n()
  const [email, setEmail] = useState(member.email)

  const save = useMutation<string, void>(async (next) => {
    await usersApi.setMemberEmail(member.user_id, organizationId, next)
  })

  return (
    <form
      className="member__email"
      onSubmit={async (event) => {
        event.preventDefault()
        const done = await save.run(email.trim())
        // A refused change (an address already taken) leaves the typed one in
        // place, so the administrator corrects a typo instead of starting over.
        if (done !== null) onDone()
      }}
    >
      <label className="field">
        <span className="visually-hidden">{t('auth.email')}</span>
        <input
          autoFocus
          type="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </label>
      <button type="submit" className="button" disabled={save.pending}>
        {save.pending ? t('app.saving') : t('app.save')}
      </button>
      <button type="button" className="link" onClick={onCancel}>
        {t('app.cancel')}
      </button>
      {save.error ? (
        <span className="field__error" role="alert">
          {save.error}
        </span>
      ) : null}
    </form>
  )
}

function AddMember({
  organizationId,
  onDone,
}: {
  organizationId: string
  onDone: () => void
}) {
  const { t } = useI18n()
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<OrganizationRole>('member')

  const add = useMutation<{ email: string; role: OrganizationRole }, void>(async (input) => {
    await organizationsApi.addMember(organizationId, input.email, input.role)
  })

  return (
    <form
      className="panel"
      onSubmit={async (event) => {
        event.preventDefault()
        const done = await add.run({ email: email.trim(), role })
        // Only close on success: a rejected invite must leave the typed address
        // in place so the person can fix a typo rather than retype it.
        if (done !== null) {
          setEmail('')
          onDone()
        }
      }}
    >
      <h2>{t('members.addTitle')}</h2>
      <p className="muted">{t('members.addHint')}</p>

      <div className="fields">
        <label className="field">
          <span>{t('members.email')}</span>
          <input
            autoFocus
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label className="field">
          <span>{t('members.role')}</span>
          <Listbox<OrganizationRole>
            value={role}
            options={(['admin', 'member', 'viewer'] as OrganizationRole[]).map((option) => ({
              value: option,
              label: t(roleLabel(option)),
              hint: t(ROLE_HINTS[option]),
            }))}
            onChange={(next) => {
              if (next !== null) setRole(next)
            }}
          />
        </label>
      </div>

      <div className="create-form__actions">
        <button type="submit" className="button button--primary" disabled={add.pending}>
          {add.pending ? t('app.loading') : t('members.add')}
        </button>
        <button type="button" className="button" onClick={onDone}>
          {t('app.cancel')}
        </button>
      </div>

      {add.error ? (
        <p className="notice notice--error" role="alert">
          {add.error}
        </p>
      ) : null}
    </form>
  )
}
