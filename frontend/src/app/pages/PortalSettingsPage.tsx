import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { DATE_FORMATS, formatDateTime, getDateFormat, setDateFormat } from '../../core/format'
import type { DateFormat } from '../../core/format'
import { useAsync, useMutation } from '../../core/hooks/useAsync'
import { useI18n } from '../../core/i18n'
import type { TranslationKey } from '../../core/i18n'
import { Listbox } from '../../core/ui/Listbox'
import { organizationsApi } from '../../core/organizations/api'
import { useOrganization } from '../../core/organizations/OrganizationContext'
import { RequiresOrganization } from '../../core/organizations/RequiresOrganization'
import { useCapabilities } from '../../core/permissions/capabilities'
import { personalSettingsApi } from '../../core/settings/api'

/**
 * Portal settings: the organization itself.
 *
 * "Portal" is the organization, not the installation. The installation has one
 * operator and no configuration surface worth a screen; what people actually
 * want to change on this route is the name and description of the place they
 * work in, and who may do what in it.
 *
 * A person's own name, password and language are one click away under their own
 * name in the header, which is where they look for them.
 */
export function PortalSettingsPage() {
  return (
    <RequiresOrganization>
      <Settings />
    </RequiresOrganization>
  )
}

const MEGABYTE = 1024 * 1024
const GIGABYTE = 1024 * MEGABYTE

function megabytesToBytes(value: number): number {
  return Number.isFinite(value) ? value * MEGABYTE : 0
}

function gigabytesToBytes(value: number): number {
  return Number.isFinite(value) ? value * GIGABYTE : 0
}

/** Bytes back into the unit the field is typed in. Both round to whole units on
 *  purpose: a limit of 1 048 575 bytes shown as "0.99" invites being "fixed" by
 *  typing a round number that means something else. */
function bytesToMegabytes(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? Math.round(value / MEGABYTE) : 0
}

function bytesToGigabytes(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? Math.round(value / GIGABYTE) : 0
}

function Settings() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const { current: organization, reload } = useOrganization()
  const organizationId = organization?.id ?? null
  const capabilities = useCapabilities(organizationId)

  const settings = useAsync(
    () => (organizationId ? organizationsApi.settings(organizationId) : Promise.resolve(null)),
    [organizationId],
  )

  const [draft, setDraft] = useState({ name: '', description: '' })
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  // The two file limits are entered in megabytes and gigabytes and stored in
  // bytes: the settings screen is read by people, the server counts bytes.
  // Only the person's own edits live in state - the fields themselves show what
  // the server holds. Seeding the inputs once from state meant a reload always
  // showed the defaults, and saving the untouched panel wrote those defaults
  // over the real limits.
  const [fileLimitDraft, setFileLimitDraft] = useState<{
    maxFileSizeMb: number
    quotaGb: number
  } | null>(null)
  const storedValues = settings.data?.values
  const maxFileSizeMb =
    fileLimitDraft?.maxFileSizeMb ?? bytesToMegabytes(storedValues?.max_file_size_bytes)
  const quotaGb = fileLimitDraft?.quotaGb ?? bytesToGigabytes(storedValues?.storage_quota_bytes)
  const editFileLimits = (patch: { maxFileSizeMb?: number; quotaGb?: number }) =>
    setFileLimitDraft({ maxFileSizeMb, quotaGb, ...patch })

  // The date format follows the same rule as the limits: the control shows what
  // the portal stores, and state holds only the change the person just made.
  // Reading it from the module instead would show whatever was in hand when the
  // page mounted - which is the default, because the portal's value arrives a
  // moment later - and the field would look like it had never been saved.
  const [dateFormatDraft, setDateFormatDraft] = useState<string | null>(null)
  const portalDateFormat =
    typeof storedValues?.date_format === 'string' ? storedValues.date_format : getDateFormat()
  const dateFormat = dateFormatDraft ?? portalDateFormat

  // A personal format outranks the portal's, and the listbox would then change a
  // value nothing reads. Saying so beats letting the person conclude that saving
  // is broken a second time.
  const personal = useAsync(
    () => (organizationId ? personalSettingsApi.read(organizationId) : Promise.resolve(null)),
    [organizationId],
  )
  const hasOwnDateFormat = typeof personal.data?.stored?.date_format === 'string'

  // Contacts (stage 2.6). Two settings, and the order they are explained in is
  // the order they matter: first whether members may choose at all, then what
  // happens to everybody who did not choose. Written as one save because a
  // portal that switched "members may choose" off while leaving its own answer
  // at "everyone" would be pretending to be strict while staying open.
  const [contactsDraft, setContactsDraft] = useState<{
    visibility: string
    selfService: boolean
  } | null>(null)
  const contactsVisibility =
    contactsDraft?.visibility ??
    (typeof storedValues?.contacts_visibility === 'string'
      ? storedValues.contacts_visibility
      : 'everyone')
  const contactsSelfService =
    contactsDraft?.selfService ?? storedValues?.contacts_self_service !== false
  const saveContacts = useMutation<Record<string, unknown>, void>(async (values) => {
    if (!organizationId) return
    await organizationsApi.updateSettings(organizationId, values)
  })
  const [fileError, setFileError] = useState<string | null>(null)

  if (!organization || organizationId === null) return null

  // The form starts from the loaded organization rather than from state seeded
  // once, so a reload after saving shows what the server actually holds.
  const name = draft.name || organization.name
  const description =
    draft.description !== ''
      ? draft.description
      : (organization.description ?? '')

  const save = useMutation<{ name: string; description: string | null }, void>(
    async (body) => {
      await organizationsApi.update(organizationId, body)
    },
  )

  const remove = useMutation<void, void>(async () => {
    await organizationsApi.delete(organizationId)
  })

  const saveFiles = useMutation<
    { max_file_size_bytes: number; storage_quota_bytes: number },
    void
  >(async (body) => {
    await organizationsApi.updateSettings(organizationId, body)
  })

  // The portal's own date format is the fallback for anybody who has not chosen
  // one, so it is saved with everything else this screen owns. A refusal is shown
  // like the limits': a setting that silently does not save is worse than one
  // that says it did not.
  const saveDateFormatSetting = useMutation<{ date_format: string }, void>(async (body) => {
    await organizationsApi.updateSettings(organizationId, body)
  })

  const mayEdit = capabilities.role === 'owner' || capabilities.role === 'admin'

  return (
    <section className="narrow">
      <h1>{t('settings.title')}</h1>

      <section className="panel">
        <h2>{t('settings.organization')}</h2>
        <form
          onSubmit={async (event) => {
            event.preventDefault()
            setError(null)
            const done = await save.run({
              name: name.trim(),
              // Always sent, null included: this field is genuinely nullable and
              // omitting the key would mean "leave it alone".
              description: description.trim() || null,
            })
            if (done !== null) {
              setDraft({ name: '', description: '' })
              reload()
            } else {
              setError(save.error)
            }
          }}
        >
          <div className="fields">
            <label className="field">
              <span>{t('settings.name')}</span>
              <input
                maxLength={200}
                value={name}
                disabled={!mayEdit}
                onChange={(event) => setDraft((state) => ({ ...state, name: event.target.value }))}
              />
            </label>
            <label className="field">
              <span>{t('settings.description')}</span>
              <textarea
                rows={3}
                maxLength={5000}
                value={description}
                disabled={!mayEdit}
                onChange={(event) =>
                  setDraft((state) => ({ ...state, description: event.target.value }))
                }
              />
            </label>
          </div>
          <dl className="meta">
            <dt>{t('settings.slug')}</dt>
            <dd>{organization.slug}</dd>
          </dl>
          {mayEdit ? (
            <div className="create-form__actions">
              <button type="submit" className="button button--primary" disabled={save.pending}>
                {save.pending ? t('app.saving') : t('app.save')}
              </button>
            </div>
          ) : null}
          {error ? (
            <p className="notice notice--error" role="alert">
              {error}
            </p>
          ) : null}
        </form>
      </section>

      <section className="panel">
        <h2>{t('settings.files')}</h2>
        <p className="muted">{t('settings.filesHint')}</p>
        <form
          onSubmit={async (event) => {
            event.preventDefault()
            setFileError(null)
            const done = await saveFiles.run({
              // Written in bytes, entered in the units people think in. Zero
              // means no limit, and it is the default a fresh portal starts at.
              max_file_size_bytes: Math.round(megabytesToBytes(maxFileSizeMb)),
              storage_quota_bytes: Math.round(gigabytesToBytes(quotaGb)),
            })
            // The draft is dropped so the fields fall back to what the server
            // now holds instead of to whatever was typed a moment ago.
            if (done !== null) {
              setFileLimitDraft(null)
              reload()
            } else setFileError(saveFiles.error)
          }}
        >
          <div className="fields">
            <label className="field">
              <span>{t('settings.dateFormat')}</span>
              <Listbox<DateFormat>
                value={dateFormat as DateFormat}
                options={DATE_FORMATS.map((id) => ({
                  value: id,
                  label: t(`dateFormat.${id}` as TranslationKey),
                }))}
                disabled={!mayEdit}
                onChange={(next) => {
                  if (next === null) return
                  setFileError(null)
                  setDateFormatDraft(next)
                  // Applied at once, before the server is told: a date format is
                  // text on every screen, and making the reader press Save to see
                  // what they just chose is how this reads as a broken setting.
                  setDateFormat(next)
                  void saveDateFormatSetting.run({ date_format: next }).then((done) => {
                    if (done === null) {
                      setFileError(saveDateFormatSetting.error)
                      return
                    }
                    // The draft is dropped *and* the settings are re-read, so the
                    // field falls back to what the server now holds rather than to
                    // the answer it still has cached from before the save.
                    setDateFormatDraft(null)
                    settings.reload()
                  })
                }}
              />
              {hasOwnDateFormat ? (
                <span className="field__note">{t('settings.dateFormatOverridden')}</span>
              ) : null}
            </label>
            <label className="field">
              <span>{t('settings.maxFileSize')}</span>
              <input
                type="number"
                min={0}
                step={1}
                value={maxFileSizeMb}
                disabled={!mayEdit}
                onChange={(event) =>
                  editFileLimits({ maxFileSizeMb: Number(event.target.value) })
                }
              />
            </label>
            <label className="field">
              <span>{t('settings.storageQuota')}</span>
              <input
                type="number"
                min={0}
                step={1}
                value={quotaGb}
                disabled={!mayEdit}
                onChange={(event) => editFileLimits({ quotaGb: Number(event.target.value) })}
              />
            </label>
          </div>
          {mayEdit ? (
            <div className="create-form__actions">
              <button type="submit" className="button button--primary" disabled={saveFiles.pending}>
                {saveFiles.pending ? t('app.saving') : t('app.save')}
              </button>
            </div>
          ) : null}
          {fileError ? (
            <p className="notice notice--error" role="alert">
              {fileError}
            </p>
          ) : null}
        </form>
      </section>

      <section className="panel">
        <h2>{t('settings.contacts')}</h2>
        <p className="muted">{t('settings.contactsHint')}</p>
        <form
          onSubmit={async (event) => {
            event.preventDefault()
            setFileError(null)
            const done = await saveContacts.run({
              contacts_visibility: contactsVisibility,
              contacts_self_service: contactsSelfService,
            })
            if (done !== null) {
              setContactsDraft(null)
              reload()
            } else setFileError(saveContacts.error)
          }}
        >
          <div className="fields">
            <label className="field">
              <span>{t('settings.contactsVisibility')}</span>
              <Listbox<string>
                value={contactsVisibility}
                options={[
                  { value: 'everyone', label: t('profile.visibilityEveryone') },
                  { value: 'admins', label: t('profile.visibilityAdmins') },
                ]}
                disabled={!mayEdit}
                onChange={(next) => {
                  if (next === null) return
                  setContactsDraft({ visibility: next, selfService: contactsSelfService })
                }}
              />
            </label>
            <label className="field checkbox">
              <input
                type="checkbox"
                checked={contactsSelfService}
                disabled={!mayEdit}
                onChange={(event) =>
                  setContactsDraft({
                    visibility: contactsVisibility,
                    selfService: event.target.checked,
                  })
                }
              />
              <span>{t('settings.contactsSelfService')}</span>
            </label>
          </div>
          {mayEdit ? (
            <div className="create-form__actions">
              <button
                type="submit"
                className="button button--primary"
                disabled={saveContacts.pending}
              >
                {saveContacts.pending ? t('app.saving') : t('app.save')}
              </button>
            </div>
          ) : null}
        </form>
      </section>

      <section className="panel">
        <h2>{t('settings.values')}</h2>
        {settings.error ? (
          <p className="notice notice--error">{settings.error}</p>
        ) : null}
        <p className="muted">
          {settings.data?.updated_at
            ? t('settings.updatedAt', { date: formatDateTime(settings.data.updated_at) })
            : t('settings.neverUpdated')}
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

      {capabilities.role === 'owner' ? (
        <section className="panel danger-zone">
          <h2>{t('settings.dangerZone')}</h2>
          {confirming ? (
            <div className="create-form__actions">
              <button
                type="button"
                className="button button--danger"
                disabled={remove.pending}
                onClick={async () => {
                  const done = await remove.run()
                  if (done !== null) navigate('/')
                  else setError(remove.error)
                }}
              >
                {t('settings.deleteOrganizationConfirm', { name: organization.name })}
              </button>
              <button type="button" className="button" onClick={() => setConfirming(false)}>
                {t('app.cancel')}
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="button button--danger"
              onClick={() => setConfirming(true)}
            >
              {t('settings.deleteOrganization')}
            </button>
          )}
        </section>
      ) : null}
    </section>
  )
}
