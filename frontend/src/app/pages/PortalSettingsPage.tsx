import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { formatDateTime } from '../../core/format'
import { useAsync, useMutation } from '../../core/hooks/useAsync'
import { useI18n } from '../../core/i18n'
import { organizationsApi } from '../../core/organizations/api'
import { useOrganization } from '../../core/organizations/OrganizationContext'
import { RequiresOrganization } from '../../core/organizations/RequiresOrganization'
import { useCapabilities } from '../../core/permissions/capabilities'

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
