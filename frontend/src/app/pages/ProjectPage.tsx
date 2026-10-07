import { Link, useNavigate, useParams } from 'react-router-dom'

import { formatDateTime } from '../../core/format'
import { useAsync } from '../../core/hooks/useAsync'
import { useI18n } from '../../core/i18n'
import { Icon } from '../../core/layout/Icon'
import { organizationsApi } from '../../core/organizations/api'
import type { Member } from '../../core/organizations/api'
import { useOrganization } from '../../core/organizations/OrganizationContext'
import { RequiresOrganization } from '../../core/organizations/RequiresOrganization'
import { useCapabilities } from '../../core/permissions/capabilities'
import { projectsApi } from '../../core/projects/api'
import { activityApi } from '../../modules/tasks/api'
import { ActivityFeed } from '../../modules/tasks/components/ActivityFeed'

/**
 * One project: what it is, and the way into its tasks.
 *
 * A separate page from the task list on purpose - §29 lists both routes, and a
 * project that has grown a description and a history deserves more than a link in
 * a list.
 */
export function ProjectPage() {
  return (
    <RequiresOrganization>
      <Project />
    </RequiresOrganization>
  )
}

function Project() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const { projectId } = useParams<{ projectId: string }>()
  const { current: organization } = useOrganization()
  const organizationId = organization?.id ?? null
  const capabilities = useCapabilities(organizationId)

  const project = useAsync(
    () =>
      organizationId && projectId
        ? projectsApi.get(projectId, organizationId)
        : Promise.resolve(null),
    [organizationId, projectId],
  )

  const roster = useAsync(
    () =>
      organizationId ? organizationsApi.members(organizationId) : Promise.resolve([] as Member[]),
    [organizationId],
  )

  const activity = useAsync(
    () =>
      organizationId
        ? activityApi.forOrganization(organizationId, 20)
        : Promise.resolve({ items: [], total: 0, limit: 0, offset: 0 }),
    [organizationId],
  )

  if (!organizationId) return null

  if (project.error) {
    return (
      <section>
        <h1>{t('projects.title')}</h1>
        <p className="notice notice--error">{project.error}</p>
        <p>
          <Link to="/projects">{t('projects.backToProjects')}</Link>
        </p>
      </section>
    )
  }

  if (!project.data) return <p className="notice">{t('app.loading')}</p>

  const current = project.data
  const actorNames = new Map(
    (roster.data ?? []).map((member) => [member.user_id, member.first_name || member.username]),
  )

  return (
    <section>
      <header className="page-header">
        <button
          type="button"
          className="page-header__back"
          onClick={() => navigate('/projects')}
        >
          <Icon name="chevron" size={14} className="page-header__back-icon" />
          <span>{t('app.back')}</span>
        </button>
        <h1>{current.name}</h1>
        <span className={`badge badge--project-${current.status}`}>{current.status}</span>
      </header>

      {current.description ? <p className="description">{current.description}</p> : null}

      <p className="card__actions">
        <Link to={`/projects/${current.id}/tasks`}>
          {capabilities.canCreateTask ? t('projects.openTaskList') : t('projects.viewTasks')}
        </Link>
        <Link to="/tasks">{t('projects.allOrganizationTasks')}</Link>
      </p>

      <section className="panel">
        <h2>{t('tasks.details')}</h2>
        <dl className="meta">
          <dt>{t('app.createdAt')}</dt>
          <dd>{formatDateTime(current.created_at)}</dd>
          <dt>{t('app.updatedAt')}</dt>
          <dd>{formatDateTime(current.updated_at)}</dd>
          <dt>{t('nav.organization')}</dt>
          <dd>{t('projects.organizationMembers', { count: (roster.data ?? []).length })}</dd>
        </dl>
      </section>

      <section className="panel">
        <h2>{t('activity.recent')}</h2>
        <ActivityFeed items={activity.data?.items ?? []} actorNames={actorNames} />
      </section>
    </section>
  )
}
