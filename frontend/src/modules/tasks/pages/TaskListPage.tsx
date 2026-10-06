import { useCallback, useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { useAsync, useMutation } from '../../../core/hooks/useAsync'
import { useI18n } from '../../../core/i18n'
import { organizationsApi } from '../../../core/organizations/api'
import { useOrganizationId } from '../../../core/organizations/OrganizationContext'
import { RequiresOrganization } from '../../../core/organizations/RequiresOrganization'
import { useCapabilities } from '../../../core/permissions/capabilities'
import { projectsApi } from '../../../core/projects/api'
import type { Project } from '../../../core/projects/api'
import { tasksApi } from '../api'
import { TaskCreateForm } from '../components/TaskCreateForm'
import { TaskFilterBar, filtersFromSearch, filtersToSearch } from '../components/TaskFilterBar'
import { TaskPagination, TaskTable } from '../components/TaskTable'
import type { Task, TaskCreate, TaskFilters } from '../types'

const PAGE_SIZE = 25

/**
 * The task list (section 30).
 *
 * Reached two ways: `/projects/:projectId/tasks` narrows to one project, and
 * `/tasks` shows the whole organization - including the inbox, the tasks that are
 * not filed under any project at all. Both go through this component because the
 * columns, filters and row actions are identical; only the API call differs, and
 * that is decided by whether a project id is in the route.
 */
export function TaskListPage() {
  return (
    <RequiresOrganization>
      <TaskList />
    </RequiresOrganization>
  )
}

function TaskList() {
  const { t } = useI18n()
  const { projectId } = useParams<{ projectId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const organizationId = useOrganizationIdOrThrow()
  const capabilities = useCapabilities(organizationId)

  const filters = useMemo(() => filtersFromSearch(searchParams.toString()), [searchParams])
  const offset = Number(searchParams.get('offset') ?? 0)

  const page = useAsync(
    () => {
      const query: TaskFilters = { ...filters, limit: PAGE_SIZE, offset }
      return projectId
        ? tasksApi.listForProject(organizationId, projectId, query)
        : tasksApi.list(organizationId, query)
    },
    [organizationId, projectId, searchParams.toString()],
  )

  const members = useAsync(
    () => organizationsApi.members(organizationId),
    [organizationId],
  )

  const project = useAsync(
    () => (projectId ? projectsApi.get(projectId, organizationId) : Promise.resolve(null)),
    [organizationId, projectId],
  )

  // Needed twice on the organization-wide list: to file a new task, and to turn
  // each row's project id into a name. One request, not one per row.
  const projects = useAsync(
    () => (projectId ? Promise.resolve([] as Project[]) : projectsApi.list(organizationId)),
    [organizationId, projectId],
  )

  const applyFilters = useCallback(
    (next: TaskFilters) => {
      // Any filter change resets to the first page: staying on page 4 of a
      // narrower result set is how a user ends up staring at an empty table.
      setSearchParams(filtersToSearch(next))
    },
    [setSearchParams],
  )

  const toggleDone = useMutation<Task, void>(async (task) => {
    await tasksApi.update(organizationId, task.id, {
      status: task.status === 'done' ? 'todo' : 'done',
    })
    page.reload()
  })

  const createTask = useMutation<TaskCreate, void>(async (input) => {
    if (projectId) {
      await tasksApi.create(organizationId, projectId, input)
    } else {
      await tasksApi.createUnfiled(organizationId, input)
    }
    page.reload()
  })

  const roster = members.data ?? []

  if (projectId && project.error) {
    return (
      <section>
        <h1>{t('projects.tasks')}</h1>
        <p className="notice notice--error">{project.error}</p>
        <p>
          <Link to="/projects">{t('projects.backToProjects')}</Link>
        </p>
      </section>
    )
  }

  const title = projectId ? (project.data?.name ?? t('projects.tasks')) : t('tasks.allTasks')

  return (
    <section>
      <header className="page-header">
        <h1>{title}</h1>
        <TaskCreateForm
          members={roster}
          projects={projects.data ?? []}
          projectId={projectId}
          disabled={!capabilities.canCreateTask}
          onCreate={(input) => createTask.runOrThrow(input)}
        />
      </header>

      <TaskFilterBar
        value={filters}
        members={roster}
        projects={projects.data ?? []}
        onChange={applyFilters}
      />

      {toggleDone.error ? (
        <p className="notice notice--error" role="alert">
          {toggleDone.error}
        </p>
      ) : null}
      {createTask.error ? (
        <p className="notice notice--error" role="alert">
          {createTask.error}
        </p>
      ) : null}
      {page.error ? <p className="notice notice--error">{page.error}</p> : null}

      {page.loading && !page.data ? <p className="notice">{t('tasks.loadingTasks')}</p> : null}

      {page.data ? (
        <>
          <TaskTable
            tasks={page.data.items}
            members={roster}
            projects={projects.data ?? []}
            projectScoped={Boolean(projectId)}
            onToggleDone={(task) => void toggleDone.run(task)}
          />
          <TaskPagination
            total={page.data.total}
            limit={page.data.limit}
            offset={page.data.offset}
            onChange={(next) => {
              const params = new URLSearchParams(searchParams)
              params.set('offset', String(next))
              setSearchParams(params)
            }}
          />
        </>
      ) : null}
    </section>
  )
}

/** Reached only inside `RequiresOrganization`, so the id is known to exist. */
function useOrganizationIdOrThrow(): string {
  const id = useOrganizationId()
  if (id === null) throw new Error('TaskList rendered without an organization')
  return id
}
