import { Link, useParams } from 'react-router-dom'

import { formatDateTime } from '../../core/format'
import { useAsync } from '../../core/hooks/useAsync'
import { organizationsApi } from '../../core/organizations/api'
import { useOrganization } from '../../core/organizations/OrganizationContext'
import { useCapabilities } from '../../core/permissions/capabilities'
import { projectsApi } from '../../core/projects/api'
import { activityApi } from '../../modules/tasks/api'
import { ActivityFeed } from '../../modules/tasks/components/ActivityFeed'

/**
 * One project: what it is, and the way into its tasks.
 *
 * A separate page from the task list on purpose - §29 lists both routes, and a
 * project that has grown a description, a team and a history deserves more than a
 * link in a list.
 */
export function ProjectPage() {
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

  const members = useAsync(
    () =>
      organizationId
        ? organizationsApi.members(organizationId)
        : Promise.resolve([]),
    [organizationId],
  )

  const activity = useAsync(
    () =>
      organizationId && projectId
        ? activityApi.forOrganization(organizationId, 20)
        : Promise.resolve({ items: [], total: 0, limit: 0, offset: 0 }),
    [organizationId, projectId],
  )

  const rosterNames = new Map(
    (members.data ?? []).map((member) => [member.user_id, member.first_name || member.username]),
  )

  if (!organization) return <p className="notice">Loading...</p>

  if (project.error) {
    return (
      <section>
        <h1>Project</h1>
        <p className="notice notice--error">{project.error}</p>
        <p>
          <Link to="/projects">Back to projects</Link>
        </p>
      </section>
    )
  }

  if (!project.data) return <p className="notice">Loading project...</p>

  const current = project.data

  return (
    <section>
      <nav className="breadcrumb">
        <Link to="/projects">Projects</Link>
        <span aria-hidden="true"> / </span>
        <span>{current.name}</span>
      </nav>

      <header className="page-header">
        <h1>{current.name}</h1>
        <span className={`badge badge--project-${current.status}`}>{current.status}</span>
      </header>

      {current.description ? <p className="description">{current.description}</p> : null}

      <p className="card__actions">
        <Link to={`/projects/${current.id}/tasks`}>
          {capabilities.canCreateTask ? 'Open task list' : 'View tasks'}
        </Link>
        <Link to="/tasks">All organization tasks</Link>
      </p>

      <section className="panel">
        <h2>Details</h2>
        <dl className="meta">
          <dt>Created</dt>
          <dd>{formatDateTime(current.created_at)}</dd>
          <dt>Updated</dt>
          <dd>{formatDateTime(current.updated_at)}</dd>
          <dt>Team</dt>
          <dd>{(members.data ?? []).length} organization members</dd>
        </dl>
      </section>

      <section className="panel">
        <h2>Recent activity</h2>
        <ActivityFeed items={activity.data?.items ?? []} actorNames={rosterNames} />
      </section>
    </section>
  )
}
