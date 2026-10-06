import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useAsync, useMutation } from '../../core/hooks/useAsync'
import { organizationsApi } from '../../core/organizations/api'
import type { Member } from '../../core/organizations/api'
import { useOrganization, rememberOrganization } from '../../core/organizations/OrganizationContext'
import { useCapabilities } from '../../core/permissions/capabilities'
import { projectsApi } from '../../core/projects/api'
import type { Project } from '../../core/projects/api'
import { ActivityFeed } from '../../modules/tasks/components/ActivityFeed'
import { activityApi } from '../../modules/tasks/api'

/**
 * Projects, and the front door of the whole product (section 29).
 *
 * A new account has no organization, so the empty state offers to create one
 * rather than showing a list of nothing with no way forward.
 */
export function ProjectsPage() {
  const navigate = useNavigate()
  const { current: organization, organizations, loading, reload } = useOrganization()
  const organizationId = organization?.id ?? null
  const capabilities = useCapabilities(organizationId)

  const projects = useAsync(
    () =>
      organizationId ? projectsApi.list(organizationId) : Promise.resolve([] as Project[]),
    [organizationId],
  )

  const activity = useAsync(
    () =>
      organizationId
        ? activityApi.forOrganization(organizationId, 15)
        : Promise.resolve({ items: [], total: 0, limit: 0, offset: 0 }),
    [organizationId],
  )

  const members = useAsync(
    () =>
      organizationId ? organizationsApi.members(organizationId) : Promise.resolve([] as Member[]),
    [organizationId],
  )

  const [projectName, setProjectName] = useState('')
  const createProject = useMutation<string, Project>(async (name) => {
    if (!organizationId) throw new Error('No organization selected')
    return projectsApi.create(organizationId, name)
  })

  const [orgName, setOrgName] = useState('')
  const createOrganization = useMutation<string, void>(async (name) => {
    const created = await organizationsApi.create(name)
    setOrgName('')
    // Record the intent, then let the provider adopt it when the list reloads.
    // Selecting directly would blank the header for a frame, because the new
    // organization is not in the old list yet.
    rememberOrganization(created.id)
    reload()
  })

  if (loading) return <p className="notice">Loading...</p>

  if (!organization) {
    return (
      <section className="onboarding">
        <h1>Welcome</h1>
        <p>You are not a member of any organization yet. Create one to get started.</p>
        <form
          className="onboarding__form"
          onSubmit={async (event) => {
            event.preventDefault()
            await createOrganization.run(orgName.trim())
          }}
        >
          <label>
            <span>Organization name</span>
            <input
              autoFocus
              required
              value={orgName}
              placeholder="Acme Inc"
              onChange={(event) => setOrgName(event.target.value)}
            />
          </label>
          <button type="submit" className="button button--primary" disabled={createOrganization.pending}>
            {createOrganization.pending ? 'Creating...' : 'Create organization'}
          </button>
          {createOrganization.error ? (
            <p className="notice notice--error" role="alert">
              {createOrganization.error}
            </p>
          ) : null}
        </form>
      </section>
    )
  }

  return (
    <section>
      <header className="page-header">
        <h1>Projects</h1>
        {capabilities.canCreateTask ? (
          <form
            className="inline-form"
            onSubmit={async (event) => {
              event.preventDefault()
              const created = await createProject.run(projectName.trim())
              if (created) {
                setProjectName('')
                navigate(`/projects/${created.id}/tasks`)
              }
            }}
          >
            <label>
              <span className="visually-hidden">New project name</span>
              <input
                value={projectName}
                placeholder="New project"
                maxLength={200}
                onChange={(event) => setProjectName(event.target.value)}
              />
            </label>
            <button type="submit" className="button button--primary" disabled={createProject.pending}>
              Create
            </button>
          </form>
        ) : null}
      </header>

      {organizations.length > 1 ? (
        <p className="muted">
          Organization: <strong>{organization.name}</strong>
        </p>
      ) : null}

      {createProject.error ? (
        <p className="notice notice--error" role="alert">
          {createProject.error}
        </p>
      ) : null}
      {projects.error ? <p className="notice notice--error">{projects.error}</p> : null}

      {projects.loading && !projects.data ? <p className="notice">Loading projects...</p> : null}

      {projects.data && projects.data.length === 0 ? (
        <p className="notice">
          No projects yet. Create the first one above to start adding tasks.
        </p>
      ) : null}

      {projects.data && projects.data.length > 0 ? (
        <ul className="cards">
          {projects.data.map((project) => (
            <li key={project.id} className="card">
              <h2>
                <Link to={`/projects/${project.id}`}>{project.name}</Link>
              </h2>
              {project.description ? <p>{project.description}</p> : null}
              <p className="muted">
                <span className={`badge badge--project-${project.status}`}>{project.status}</span>
              </p>
              <p className="card__actions">
                <Link to={`/projects/${project.id}`}>Overview</Link>
                <Link to={`/projects/${project.id}/tasks`}>Tasks</Link>
              </p>
            </li>
          ))}
        </ul>
      ) : null}

      <section className="panel">
        <h2>Recent activity</h2>
        <ActivityFeed
          items={activity.data?.items ?? []}
          actorNames={new Map(
            (members.data ?? []).map((member) => [
              member.user_id,
              member.first_name || member.username,
            ]),
          )}
        />
      </section>
    </section>
  )
}
