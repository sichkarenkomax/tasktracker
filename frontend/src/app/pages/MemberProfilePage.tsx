import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useAuth } from '../../core/auth/AuthContext'
import { formatDate } from '../../core/format'
import { useAsync, useMutation } from '../../core/hooks/useAsync'
import { useI18n } from '../../core/i18n'
import type { TranslationKey } from '../../core/i18n'
import { Icon } from '../../core/layout/Icon'
import { organizationsApi } from '../../core/organizations/api'
import type { OrganizationRole, OrgStructure } from '../../core/organizations/api'
import { useOrganization } from '../../core/organizations/OrganizationContext'
import { useCapabilities } from '../../core/permissions/capabilities'
import { Listbox } from '../../core/ui/Listbox'
import { Avatar } from '../../core/users/Avatar'
import { DEFAULT_COUNTRY, NEW_PHONE, PhoneFields, PhoneLine } from '../../core/users/PhoneFields'
import type { PhoneDraft } from '../../core/users/PhoneFields'
import { formatPhone, isValidPhone, phoneDigits, toE164 } from '../../core/users/phoneMask'
import type { PhoneKind } from '../../core/users/phoneMask'
import { usersApi } from '../../core/users/api'
import type { MemberProfile } from '../../core/users/api'
import { UserStatusLabel } from '../../core/users/UserStatusLabel'

/** "No department", "no position" - a real answer, not an empty one. */
const ANY = 'any'

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

  // Above the early returns, deliberately. A hook called after one of them is a
  // hook that sometimes does not run: the first render returns "loading" and
  // never calls it, the second calls it, and React answers with "rendered more
  // hooks than during the previous render" - which unmounts the whole tree. The
  // page is then black, the back button does nothing because the router went
  // with it, and only a reload recovers. The same reason the editor below takes
  // its flags as props instead of asking for capabilities itself.
  const capabilities = useCapabilities(organizationId)

  if (profile.loading && !profile.data) return <p className="notice">{t('app.loading')}</p>

  if (profile.error) {
    return (
      <section className="narrow">
        <p className="notice notice--error" role="alert">
          {profile.error}
        </p>
        <Link className="button" to="/users">
          {t('people.title')}
        </Link>
      </section>
    )
  }

  const person = profile.data
  if (!person) return null

  const name = person.first_name || person.username
  const isMe = person.id === user?.id
  // What the editor offers is narrowed to what the server will check: a disabled
  // account belongs to the installation rather than to this organization, so it
  // does not belong on the same form as a name.
  const mayEditProfile = capabilities.canUpdateUser && !isMe
  const mayEditStructure = capabilities.canEditOrgStructure && !isMe
  const mayLock = !!user?.is_superuser && !isMe
  const mayEditAnything = mayEditProfile || mayEditStructure || mayLock

  return (
    <section className="narrow">
      <header className="page-header">
        {/* Back to the one people list (2.17). `/members` is a redirect now, so
            linking to it would work and still be the wrong thing to say. */}
        <Link className="page-header__back" to="/users">
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
{/* Presence, not "last signed in" (2.9): the first answers "is this
              person at their desk", the second only "did they once type a
              password today". And when their answer hides it, the row is not
              drawn at all - a dash here would say "we know and you may not",
              which is more than the card is entitled to say. */}
          {person.last_seen_visible ? (
            <>
              <dt>{t('profile.presence')}</dt>
              <dd>
                {/* Through the status contract (2.10), not straight to presence:
                    a status module replaces this line without knowing this file
                    exists, and with nothing installed it renders exactly what it
                    rendered before. */}
                <UserStatusLabel
                  subject={{
                    userId: person.id,
                    presenceVisible: person.last_seen_visible,
                    lastSeen: person.last_seen,
                    viewerId: user?.id ?? '',
                    role: person.role,
                  }}
                />
              </dd>
            </>
          ) : null}
</dl>

        {/* A link, not a tab: the journal is somebody else's screen, and a card
            that is already three panels long does not need a fourth (2.11). */}
        <p className="muted">
          <Link to={`/users/${person.id}/activity`} className="link">
            {t('journal.title')}
          </Link>
        </p>
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
                    <PhoneLine number={phone.number} kind={phone.kind} />
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

      {mayEditAnything && organizationId ? (
        <MemberEditor
          profile={person}
          organizationId={organizationId}
          mayEditProfile={mayEditProfile}
          mayEditStructure={mayEditStructure}
          mayLock={mayLock}
          onSaved={() => profile.reload()}
        />
      ) : null}

      {isMe ? (
        <p className="muted">
          <Link to="/users/me">{t('profile.editOwn')}</Link>
        </p>
      ) : null}
    </section>
  )
}

/**
 * What an administrator may change about somebody (stage 2.18).
 *
 * A panel under the card rather than a modal: the person being edited stays on
 * screen while the form is open, so "did it save?" is answered by the card
 * itself. The project has no modal component, and inventing one for a single
 * form would be a component with exactly one user.
 *
 * Everything is one request. The server checks every permission before it
 * writes anything, so a refused field cannot leave a half-saved person behind -
 * which is the whole reason this is one form and not four.
 */
function MemberEditor({
  profile,
  organizationId,
  mayEditProfile,
  mayEditStructure,
  mayLock,
  onSaved,
}: {
  profile: MemberProfile
  organizationId: string
  mayEditProfile: boolean
  mayEditStructure: boolean
  mayLock: boolean
  onSaved: () => void
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [done, setDone] = useState(false)

  const structure = useAsync(
    () => (open ? organizationsApi.structure(organizationId) : Promise.resolve(null)),
    [open, organizationId],
  )

  const save = useMutation<Parameters<typeof usersApi.updateMember>[2], void>(async (changes) => {
    await usersApi.updateMember(profile.id, organizationId, changes)
  })

  if (!open) {
    return (
      <section className="panel">
        <button
          type="button"
          className="button button--primary"
          onClick={() => {
            setOpen(true)
            setDone(false)
          }}
        >
          <Icon name="edit" size={15} />
          {t('profile.editMember')}
        </button>
        <p className="muted">{t('profile.editMemberHint')}</p>
      </section>
    )
  }

  return (
    <MemberEditorForm
      profile={profile}
      organizationId={organizationId}
      structure={structure.data}
      mayEditProfile={mayEditProfile}
      mayEditStructure={mayEditStructure}
      mayLock={mayLock}
      saving={save.pending}
      error={save.error}
      saved={done}
      onCancel={() => setOpen(false)}
      onSave={async (changes) => {
        setDone(false)
        const result = await save.run(changes)
        if (result === null) return
        setDone(true)
        onSaved()
      }}
    />
  )
}

function MemberEditorForm({
  profile,
  organizationId,
  structure,
  mayEditProfile,
  mayEditStructure,
  mayLock,
  saving,
  error,
  saved,
  onCancel,
  onSave,
}: {
  profile: MemberProfile
  organizationId: string
  structure: OrgStructure | null
  mayEditProfile: boolean
  mayEditStructure: boolean
  mayLock: boolean
  saving: boolean
  error: string | null
  saved: boolean
  onCancel: () => void
  onSave: (changes: Parameters<typeof usersApi.updateMember>[2]) => Promise<void>
}) {
  const { t } = useI18n()
  const [firstName, setFirstName] = useState(profile.first_name ?? '')
  const [lastName, setLastName] = useState(profile.last_name ?? '')
  const [email, setEmail] = useState(profile.email ?? '')
  const [birthday, setBirthday] = useState(profile.birthday ?? '')
  const [role, setRole] = useState<OrganizationRole>((profile.role as OrganizationRole) ?? 'member')
const [department, setDepartment] = useState(profile.department_id ?? ANY)
  const [position, setPosition] = useState(profile.position_id ?? ANY)
  const [manager, setManager] = useState(profile.manager_id ?? ANY)
  const [status, setStatus] = useState<'active' | 'invited' | 'disabled'>(
    (profile.status as 'active' | 'invited' | 'disabled') ?? 'active',
  )
  // The numbers come in as drafts rather than ids: the mask and the kind belong
  // to what is being typed, and a list of ids cannot express "this one changed
  // from work to home" or "this one is new".
  const [phones, setPhones] = useState<PhoneDraft[]>(() =>
    profile.phones.map((phone) => ({
      number: formatPhone(phone.number, phone.country),
      country: phone.country ?? DEFAULT_COUNTRY,
      kind: phone.kind,
    })),
  )
  // The row being written. Kept apart from the saved ones so "add" means
  // "remember this one", not "this field is the list".
  const [added, setAdded] = useState<PhoneDraft>(NEW_PHONE)

  /** A number the library cannot make sense of, in any row.
   *
   * The rows show their own error, and the save is blocked while one is broken:
   * "the numbers are a list, so drop the ones that do not parse" would delete a
   * colleague's number because the administrator was halfway through typing it.
   */
  const phonesBroken = phones.some(
    (phone) => phoneDigits(phone.number) !== '' && toE164(phone.number, phone.country) === null,
  )

  // Only the keys the administrator actually touched are sent. The rest are
  // "leave it alone", and sending a value the screen merely happened to have
  // loaded is how a form quietly rewrites a field somebody else edited in the
  // meantime.
  const changes = (): Parameters<typeof usersApi.updateMember>[2] => {
    const body: Parameters<typeof usersApi.updateMember>[2] = {}
    if (firstName !== (profile.first_name ?? '')) body.first_name = firstName
    if (lastName !== (profile.last_name ?? '')) body.last_name = lastName
    // An empty address field cannot be sent as "" - the server would refuse it
    // - and an administrator who clears it has to be told why nothing happens.
    if (email !== (profile.email ?? '')) body.email = email
    if (birthday !== (profile.birthday ?? '')) body.birthday = birthday === '' ? null : birthday
    if (role !== profile.role) body.role = role as OrganizationRole
    if (department !== (profile.department_id ?? ANY)) body.department_id = department === ANY ? null : department
    if (position !== (profile.position_id ?? ANY)) body.position_id = position === ANY ? null : position
    if (manager !== (profile.manager_id ?? ANY)) body.manager_id = manager === ANY ? null : manager
    if (status !== profile.status) body.status = status
    // Numbers travel in E.164 - exactly what the server stores - so two
    // spellings of one call are not a "change" that quietly resets a kind, and
    // the comparison below is against the same shape the server will hold.
    const sent = phones.flatMap<{ number: string; kind: PhoneKind; country: string | null }>(
      (phone) => {
        const number = toE164(phone.number, phone.country)
        return number === null ? [] : [{ number, kind: phone.kind, country: phone.country }]
      },
    )
    const before = profile.phones.map((phone) => ({
      number: phone.number,
      kind: phone.kind,
      country: phone.country,
    }))
    if (JSON.stringify(sent) !== JSON.stringify(before) && !phonesBroken) body.phones = sent
    return body
  }

  // Who can be a manager: anybody in this organization but the person being
  // edited, who cannot report to themselves. Loaded here rather than passed in
  // because the editor is rendered from two places and both need the same list.
  const managers = useAsync(
    () => (organizationId ? organizationsApi.members(organizationId) : Promise.resolve([])),
    [organizationId],
  )

  return (
    <section className="panel">
      <h2>{t('profile.editMember')}</h2>
      <p className="muted">{t('profile.editMemberHint')}</p>

      <form
        onSubmit={async (event) => {
          event.preventDefault()
          await onSave(changes())
        }}
      >
        <div className="fields">
          {mayEditProfile ? (
            <>
              <label className="field">
                <span>{t('auth.firstName')}</span>
                <input
                  maxLength={64}
                  value={firstName}
                  onChange={(event) => setFirstName(event.target.value)}
                />
              </label>
              <label className="field">
                <span>{t('auth.lastName')}</span>
                <input
                  maxLength={64}
                  value={lastName}
                  onChange={(event) => setLastName(event.target.value)}
                />
              </label>
              <label className="field">
                <span>{t('auth.email')}</span>
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </label>
              <label className="field">
                <span>{t('profile.birthday')}</span>
                <input
                  type="date"
                  value={birthday}
                  max={new Date().toISOString().slice(0, 10)}
                  onChange={(event) => setBirthday(event.target.value)}
                />
              </label>
            </>
          ) : null}

          {mayEditStructure ? (
            <>
              <label className="field">
                <span>{t('people.column.role')}</span>
                <Listbox<OrganizationRole>
                  value={role}
                  options={(['admin', 'member', 'viewer'] as OrganizationRole[]).map((option) => ({
                    value: option,
                    label: t(`role.${option}` as TranslationKey),
                  }))}
                  onChange={(next) => {
                    if (next !== null) setRole(next as OrganizationRole)
                  }}
                />
              </label>
              <label className="field">
                <span>{t('people.column.department')}</span>
                <Listbox<string>
                  value={department}
                  options={[
                    { value: ANY, label: t('people.none') },
                    ...(structure?.departments ?? []).map((item) => ({
                      value: item.id,
                      label: item.name,
                    })),
                  ]}
                  disabled={!structure}
                  onChange={(next) => {
                    if (next !== null) setDepartment(next)
                  }}
                />
              </label>
<label className="field">
                <span>{t('people.column.position')}</span>
                <Listbox<string>
                  value={position}
                  options={[
                    { value: ANY, label: t('people.none') },
                    ...(structure?.positions ?? []).map((item) => ({
                      value: item.id,
                      label: item.title,
                    })),
                  ]}
                  disabled={!structure}
                  onChange={(next) => {
                    if (next !== null) setPosition(next)
                  }}
                />
              </label>
              <label className="field">
                <span>{t('people.column.manager')}</span>
                <Listbox<string>
                  value={manager}
                  searchable
                  searchPlaceholder={t('listbox.searchPlaceholder')}
                  nothingFoundLabel={t('listbox.nothingFound')}
                  options={[
                    { value: ANY, label: t('people.none') },
                    ...(managers.data ?? [])
                      // Reporting to yourself is not a reporting line, so the
                      // person being edited is not offered as their own manager.
                      .filter((person) => person.user_id !== profile.id)
                      .map((person) => ({
                        value: person.user_id,
                        label: [person.first_name, person.last_name].filter(Boolean).join(' ') || person.username,
                      })),
                  ]}
                  disabled={managers.loading}
                  onChange={(next) => {
                    if (next !== null) setManager(next)
                  }}
                />
              </label>
            </>
          ) : null}

{mayEditProfile ? (
            // One grid cell for the whole of it. `.fields` lays its children out
            // in as many columns as fit, and the phones used to be three of
            // them - the heading, the list and the "add" form side by side,
            // each squeezed into a twelfth of the panel.
            <div className="phones-block">
              <h3>{t('profile.phones')}</h3>
              {phones.length === 0 ? (
                <p className="muted">{t('profile.noPhones')}</p>
              ) : (
                <ul className="phones-editor">
                  {phones.map((phone, index) => (
                    <li key={index}>
                      <PhoneFields
                        value={phone}
                        id={`editor-phone-${index}`}
                        onChange={(next) =>
                          setPhones((current) =>
                            current.map((item, at) => (at === index ? next : item)),
                          )
                        }
                      />
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={t('profile.removePhone')}
                        onClick={() =>
                          setPhones((current) => current.filter((_, at) => at !== index))
                        }
                      >
                        <Icon name="close" size={13} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <div className="contacts-add">
                <PhoneFields
                  value={added}
                  onChange={setAdded}
                  numberPlaceholder={t('profile.addPhone')}
                />
                <button
                  type="button"
                  className="button"
                  disabled={!isValidPhone(added.number, added.country)}
                  onClick={() => {
                    setPhones((current) => [...current, added])
                    setAdded(NEW_PHONE)
                  }}
                >
                  {t('profile.add')}
                </button>
              </div>
            </div>
          ) : null}

          {mayLock ? (
            <label className="field">
              <span>{t('people.column.status')}</span>
              <Listbox<string>
                value={status}
                options={(['active', 'invited', 'disabled'] as const).map((option) => ({
                  value: option,
                  label: t(`people.status.${option}` as TranslationKey),
                }))}
                onChange={(next) => {
                  if (next !== null) setStatus(next as 'active' | 'invited' | 'disabled')
                }}
              />
            </label>
          ) : null}
        </div>

        {error ? (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        ) : null}
        {saved && !error ? <p className="notice">{t('profile.editSaved')}</p> : null}

        <div className="create-form__actions">
          <button
          type="submit"
          className="button button--primary"
          disabled={saving || phonesBroken}
          title={phonesBroken ? t('profile.phoneIncomplete') : undefined}
        >
            {saving ? t('app.saving') : t('app.save')}
          </button>
          <button type="button" className="button" onClick={onCancel}>
            {t('app.cancel')}
          </button>
        </div>
      </form>
    </section>
  )
}