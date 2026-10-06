import { useCallback, useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { useAsync, useMutation } from '../../../core/hooks/useAsync'
import { organizationsApi } from '../../../core/organizations/api'
import type { Member } from '../../../core/organizations/api'
import { useOrganization } from '../../../core/organizations/OrganizationContext'
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
 * `/tasks` shows the whole organization. Both go through the same component
 * because the columns, filters and row actions are identical - only the API call
 * differs, and that is decided by whether a project id is in the route.
 */
export function TaskListPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const { current: organization, loading: orgLoading } = useOrganization()

  const filters = useMemo(() => filtersFromSearch(searchParams.toString()), [searchParams])
  const offset = Number(searchParams.get('offset') ?? 0)

  const organizationId = organization?.id ?? null
  const capabilities = useCapabilities(organizationId)

  const page = useAsync(
    () => {
      if (!organizationId) return Promise.resolve(null)
      const query: TaskFilters = { ...filters, limit: PAGE_SIZE, offset }
      return projectId
        ? tasksApi.listForProject(organizationId, projectId, query)
        : tasksApi.list(organizationId, query)
    },
    [organizationId, projectId, searchParams.toString(), offset],
  )

  const members = useAsync(
    () =>
      organizationId ? organizationsApi.members(organizationId) : Promise.resolve([] as Member[]),
    [organizationId],
  )

  const project = useAsync(
    () =>
      organizationId && projectId
        ? projectsApi.get(projectId, organizationId)
        : Promise.resolve(null),
    [organizationId, projectId],
  )

  // The organization-wide list mixes projects, so each row needs its project's
  // name. Fetched once per organization rather than per row: the list endpoint
  // returns task ids, and one request per task to learn what it belongs to is
  // how a 25-row page becomes 25 requests.
  const allProjects = useAsync(
    () =>
      organizationId && !projectId
        ? projectsApi.list(organizationId)
        : Promise.resolve([] as Project[]),
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
    if (!organizationId) return
    await tasksApi.update(organizationId, task.id, {
      status: task.status === 'done' ? 'todo' : 'done',
    })
    page.reload()
  })

  const createTask = useMutation<TaskCreate, void>(async (input) => {
    if (!organizationId || !projectId) return
    await tasksApi.create(organizationId, projectId, input)
    page.reload()
  })

  if (orgLoading || !organization) {
    return <p className="notice">Loading...</p>
  }

  if (projectId && !project.data) {
    return (
      <section>
        <h1>Project</h1>
        {project.error ? <p className="notice notice--error">{project.error}</p> : null}
        <p>
          <Link to="/projects">Back to projects</Link>
        </p>
      </section>
    )
  }

  const title = projectId ? (project.data?.name ?? 'Project') : 'All tasks'
  const projectNames = new Map((allProjects.data ?? []).map((item) => [item.id, item.name]))

  return (
    <section>
      <header className="page-header">
        <h1>{title}</h1>
        {projectId ? (
          <TaskCreateForm
            members={members.data ?? []}
            disabled={!capabilities.canCreateTask}
            onCreate={(input) => createTask.runOrThrow(input)}
          />
        ) : null}
      </header>

      <TaskFilterBar
        value={filters}
        members={members.data ?? []}
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

      {page.loading && !page.data ? <p className="notice">Loading tasks...</p> : null}

      {page.data ? (
        <>
          <TaskTable
            tasks={page.data.items}
            members={members.data ?? []}
            projectScoped={Boolean(projectId)}
            projectNames={projectNames}
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
