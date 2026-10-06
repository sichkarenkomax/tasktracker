import { useState } from 'react'
import type { ReactElement } from 'react'

import { useI18n } from '../i18n'
import { useMutation } from '../hooks/useAsync'
import { organizationsApi } from './api'
import type { Organization } from './api'
import { useOrganization } from './OrganizationContext'

/**
 * The form a person needs when they have no organization at all.
 *
 * Extracted from the projects page because the gate below needs it too: without
 * it, every page that depends on a tenant renders its own "Loading..." forever,
 * which is exactly what a brand-new account sees.
 */
export function CreateOrganizationForm() {
  const { t } = useI18n()
  const { reload } = useOrganization()
  const [name, setName] = useState('')

  const create = useMutation<string, Organization>(async (value) => {
    const organization = await organizationsApi.create(value)
    reload()
    return organization
  })

  return (
    <form
      className="onboarding__form"
      onSubmit={async (event) => {
        event.preventDefault()
        const trimmed = name.trim()
        if (!trimmed) return
        const created = await create.run(trimmed)
        // Only clear on success: a rejected create must leave the typed name in
        // place so the person can fix a typo instead of retyping it.
        if (created !== null) setName('')
      }}
    >
      <label>
        <span>{t('auth.organizationName')}</span>
        <input
          autoFocus
          required
          maxLength={200}
          value={name}
          placeholder={t('onboarding.namePlaceholder')}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <button type="submit" className="button button--primary" disabled={create.pending}>
        {create.pending ? t('app.loading') : t('auth.createOrganization')}
      </button>
      {create.error ? (
        <p className="notice notice--error" role="alert">
          {create.error}
        </p>
      ) : null}
    </form>
  )
}

/**
 * Gate for every page that cannot work without an organization.
 *
 * The important case is the third one. `loading` false with no organization means
 * the person genuinely has none - a new account - and the honest answer is an
 * invitation to create one. Rendering "Loading..." instead leaves them staring
 * at a spinner forever with no way forward, and no error either, because nothing
 * failed.
 */
export function RequiresOrganization({ children }: { children: ReactElement }) {
  const { t } = useI18n()
  const { current, loading, error, organizations } = useOrganization()

  if (loading) {
    return <p className="notice">{t('app.loading')}</p>
  }

  if (error) {
    return (
      <p className="notice notice--error" role="alert">
        {error}
      </p>
    )
  }

  if (!current) {
    return (
      <section className="onboarding">
        <h1>{t('auth.welcome')}</h1>
        <p>{t('onboarding.createFirst')}</p>
        <CreateOrganizationForm />
        {organizations.length === 0 ? null : (
          <p className="muted">{t('auth.noOrganization')}</p>
        )}
      </section>
    )
  }

  return children
}
