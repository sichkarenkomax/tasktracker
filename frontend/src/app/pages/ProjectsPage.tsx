import { useState } from 'react'
import { Link } from 'react-router-dom'

import { useAsync, useMutation } from '../../core/hooks/useAsync'
import { useI18n } from '../../core/i18n'
import { Icon } from '../../core/layout/Icon'
import { organizationsApi } from '../../core/organizations/api'
import type { Member } from '../../core/organizations/api'
import { useOrganization } from '../../core/organizations/OrganizationContext'
import { RequiresOrganization } from '../../core/organizations/RequiresOrganization'
import { useCapabilities } from '../../core/permissions/capabilities'
import { projectsApi } from '../../core/projects/api'
import type { Project } from '../../core/projects/api'
import { activityApi } from '../../core/activity/api'
import { ActivityFeed } from '../../core/activity/ActivityFeed'

/**
 * Projects, and the front door of the product (section 29).
 *
 * A new account has no organization, so the gate above handles that case; this
 * page only ever sees somebody who has one.
 */
export function ProjectsPage() {
  return (
    <RequiresOrganization>
      <Projects />
    </RequiresOrganization>
  )
}

function Projects() {
  const { t } = useI18n()
  const { current: organization } = useOrganization()
  const organizationId = organization?.id ?? null
  const capabilities = useCapabilities(organizationId)
  const [name, setName] = useState('')

  const projects = useAsync(
    () => (organizationId ? projectsApi.list(organizationId) : Promise.resolve([] as Project[])),
    [organizationId],
  )

  const activity = useAsync(
    () =>
      organizationId
        ? activityApi.forOrganization(organizationId, 15)
        : Promise.resolve({ items: [], total: 0, limit: 0, offset: 0 }),
    [organizationId],
  )

  const roster = useAsync(
    () => (organizationId ? organizationsApi.members(organizationId) : Promise.resolve([] as Member[])),
    [organizationId],
  )

  const create = useMutation<string, Project>(async (value) => {
    if (!organizationId) throw new Error(t('error.generic'))
    return projectsApi.create(organizationId, value)
  })

  if (!organizationId) return null

  const actorNames = new Map(
    (roster.data ?? []).map((member) => [
      member.user_id,
      member.first_name || member.username,
    ]),
  )

  return (
    <section>
      <header className="page-header">
        <h1>{t('projects.title')}</h1>
        {capabilities.canCreateTask ? (
          <form
            className="inline-form"
            onSubmit={async (event) => {
              event.preventDefault()
              const trimmed = name.trim()
              if (!trimmed) return
              const created = await create.run(trimmed)
              if (created !== null) setName('')
            }}
          >
            <label>
              <span className="visually-hidden">{t('projects.new')}</span>
              <input
                value={name}
                placeholder={t('projects.new')}
                maxLength={200}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <button type="submit" className="button button--primary" disabled={create.pending}>
              <Icon name="plus" size={15} />
              {t('app.create')}
            </button>
          </form>
        ) : null}
      </header>

      {create.error ? (
        <p className="notice notice--error" role="alert">
          {create.error}
        </p>
      ) : null}
      {projects.error ? (
        <p className="notice notice--error" role="alert">
          {projects.error}
        </p>
      ) : null}
      {projects.loading && !projects.data ? <p className="notice">{t('app.loading')}</p> : null}

      {projects.data && projects.data.length === 0 ? (
        <p className="notice">{t('projects.empty')}</p>
      ) : null}

      {projects.data && projects.data.length > 0 ? (
        <ul className="cards">
          {projects.data.map((project) => (
            <li key={project.id} className="card">
              <h2>
                <Link to={`/projects/${project.id}`}>{project.name}</Link>
              </h2>
              {project.description ? <p>{project.description}</p> : null}
              <p>
                <span className={`badge badge--project-${project.status}`}>{project.status}</span>
              </p>
              <p className="card__actions">
                <Link to={`/projects/${project.id}`}>{t('projects.overview')}</Link>
                <Link to={`/projects/${project.id}/tasks`}>{t('projects.tasks')}</Link>
              </p>
            </li>
          ))}
        </ul>
      ) : null}

      <section className="panel">
        <h2>{t('activity.recent')}</h2>
        <ActivityFeed items={activity.data?.items ?? []} actorNames={actorNames} />
      </section>
    </section>
  )
}
