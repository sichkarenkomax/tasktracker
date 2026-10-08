import { useNavigate, useParams } from 'react-router-dom'

import { useAsync } from '../../../core/hooks/useAsync'
import { useI18n } from '../../../core/i18n'
import { Icon } from '../../../core/layout/Icon'
import { organizationsApi } from '../../../core/organizations/api'
import { useOrganizationId } from '../../../core/organizations/OrganizationContext'
import { RequiresOrganization } from '../../../core/organizations/RequiresOrganization'
import type { Project } from '../../../core/projects/api'
import { projectsApi } from '../../../core/projects/api'
import { tasksApi } from '../api'
import { TaskCreateForm } from '../components/TaskCreateForm'
import type { TaskCreate } from '../types'

/**
 * The create-a-task page (`/tasks/new`, and the project-scoped twin).
 *
 * It replaced a form that unfolded in the list's header. A form there is not
 * merely cramped: it appears *above* the table, so every row the person was
 * reading moves down under the cursor while they type. On its own page the form
 * has room for what the roadmap still owes it (attachments, the planned window),
 * the URL can be linked to ("create a task in this project"), and the list is
 * one Back away with its filters exactly as they were.
 *
 * The project-scoped route is not a nicety: it is where the project comes from,
 * so the field does not have to be offered for a choice that has already been
 * made by the address bar.
 */
export function TaskCreatePage() {
  return (
    <RequiresOrganization>
      <Create />
    </RequiresOrganization>
  )
}

function Create() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const { projectId } = useParams<{ projectId: string }>()
  const organizationId = useOrganizationId() ?? ''

  const members = useAsync(() => organizationsApi.members(organizationId), [organizationId])
  const projects = useAsync(
    () => (projectId ? Promise.resolve([] as Project[]) : projectsApi.list(organizationId)),
    [organizationId, projectId],
  )
  const project = useAsync(
    () => (projectId ? projectsApi.get(projectId, organizationId) : Promise.resolve(null)),
    [organizationId, projectId],
  )

  /** Where Cancel goes: back to the list this page was reached from. */
  const listPath = projectId ? `/projects/${projectId}/tasks` : '/tasks'

  async function create(input: TaskCreate) {
    const created = projectId
      ? await tasksApi.create(organizationId, projectId, input)
      : await tasksApi.createUnfiled(organizationId, input)
    // Into the task that was just written, not back to the list: the reason for
    // writing it down is usually what comes next - a description, a file, a
    // participant - and that is all on its card.
    navigate(`/tasks/${created.id}`)
  }

  return (
    <section className="narrow">
      <button type="button" className="button button--ghost" onClick={() => navigate(listPath)}>
        <Icon name="chevron" size={14} className="back-chevron" />
        {project.data?.name ?? t('tasks.allTasks')}
      </button>

      <h1>{t('tasks.newTask')}</h1>
      {project.data?.name ? <p className="muted">{project.data.name}</p> : null}

      <TaskCreateForm
        members={members.data ?? []}
        projects={projects.data ?? []}
        projectId={projectId}
        onCreate={create}
        onCancel={() => navigate(listPath)}
      />
    </section>
  )
}