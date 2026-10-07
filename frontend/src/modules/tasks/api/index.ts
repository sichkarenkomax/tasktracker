import { api, buildQuery } from '../../../core/api/client'
import type { Query } from '../../../core/api/client'
import type {
  ActivityPage,
  Comment,
  CommentPage,
  ParticipantRole,
  Task,
  TaskCreate,
  TaskFilters,
  TaskPage,
  TaskParticipant,
  TaskUpdate,
} from '../types'

/**
 * Typed wrappers over the Tasks endpoints.
 *
 * Every call carries `organization_id` because the API takes the tenant as a
 * query parameter (section 26). Funnelling it through one argument here means no
 * caller can forget it, and the query string is built in exactly one place.
 */
function tenant(organizationId: string, extra: Query = {}): Query {
  return { organization_id: organizationId, ...extra }
}

/**
 * The filter object doubles as the query object - the keys in `TaskFilters` are
 * already the parameter names the API expects, and the multi-valued ones stay
 * arrays so `buildQuery` emits repeated keys rather than a comma-joined string
 * the server cannot parse.
 */
function filtersToQuery(filters: TaskFilters): Query {
  return { ...filters }
}

export const tasksApi = {
  list(organizationId: string, filters: TaskFilters = {}): Promise<TaskPage> {
    return api.get<TaskPage>(`/tasks${buildQuery(tenant(organizationId, filtersToQuery(filters)))}`)
  },

  listForProject(
    organizationId: string,
    projectId: string,
    filters: TaskFilters = {},
  ): Promise<TaskPage> {
    return api.get<TaskPage>(
      `/projects/${projectId}/tasks${buildQuery(tenant(organizationId, filtersToQuery(filters)))}`,
    )
  },

  get(organizationId: string, taskId: string): Promise<Task> {
    return api.get<Task>(`/tasks/${taskId}${buildQuery(tenant(organizationId))}`)
  },

  create(organizationId: string, projectId: string, payload: TaskCreate): Promise<Task> {
    return api.post<Task>(`/projects/${projectId}/tasks${buildQuery(tenant(organizationId))}`, {
      ...payload,
      description: payload.description ?? null,
      priority: payload.priority ?? null,
      due_date: payload.due_date ?? null,
      assignee_id: payload.assignee_id ?? null,
    })
  },

  /**
   * Create a task that belongs to the organization but to no project yet.
   *
   * The flat route rather than the nested one, because there is no project to
   * nest under. `project_id` may still be passed when the person is filing it
   * straight away.
   */
  createUnfiled(organizationId: string, payload: TaskCreate): Promise<Task> {
    return api.post<Task>(`/tasks${buildQuery(tenant(organizationId))}`, {
      ...payload,
      description: payload.description ?? null,
      priority: payload.priority ?? null,
      due_date: payload.due_date ?? null,
      assignee_id: payload.assignee_id ?? null,
      project_id: payload.project_id ?? null,
    })
  },

  update(organizationId: string, taskId: string, payload: TaskUpdate): Promise<Task> {
    return api.patch<Task>(`/tasks/${taskId}${buildQuery(tenant(organizationId))}`, payload)
  },

  remove(organizationId: string, taskId: string): Promise<void> {
    return api.delete<void>(`/tasks/${taskId}${buildQuery(tenant(organizationId))}`)
  },

  listComments(organizationId: string, taskId: string): Promise<CommentPage> {
    return api.get<CommentPage>(`/tasks/${taskId}/comments${buildQuery(tenant(organizationId))}`)
  },

  addComment(organizationId: string, taskId: string, content: string): Promise<Comment> {
    return api.post<Comment>(`/tasks/${taskId}/comments${buildQuery(tenant(organizationId))}`, {
      content,
    })
  },

  removeComment(organizationId: string, taskId: string, commentId: string): Promise<void> {
    return api.delete<void>(
      `/tasks/${taskId}/comments/${commentId}${buildQuery(tenant(organizationId))}`,
    )
  },

  listParticipants(organizationId: string, taskId: string): Promise<TaskParticipant[]> {
    return api.get<TaskParticipant[]>(
      `/tasks/${taskId}/participants${buildQuery(tenant(organizationId))}`,
    )
  },

  addParticipant(
    organizationId: string,
    taskId: string,
    userId: string,
    role: ParticipantRole,
  ): Promise<TaskParticipant> {
    return api.post<TaskParticipant>(
      `/tasks/${taskId}/participants${buildQuery(tenant(organizationId))}`,
      { user_id: userId, role },
    )
  },

  removeParticipant(
    organizationId: string,
    taskId: string,
    userId: string,
    role: ParticipantRole,
  ): Promise<void> {
    return api.delete<void>(
      `/tasks/${taskId}/participants/${userId}${buildQuery(tenant(organizationId, { role }))}`,
    )
  },
}

export const activityApi = {
  forOrganization(organizationId: string, limit = 25): Promise<ActivityPage> {
    return api.get<ActivityPage>(
      `/activity${buildQuery({ organization_id: organizationId, limit })}`,
    )
  },

  /**
   * The feed of one entity.
   *
   * Used by the task page, where §31 puts Activity next to Comments. A comment
   * publishes `entity_type=task`, so asking per task returns comment activity too.
   */
  forEntity(
    organizationId: string,
    entityType: string,
    entityId: string,
    limit = 25,
  ): Promise<ActivityPage> {
    return api.get<ActivityPage>(
      `/activity/entity/${entityType}/${entityId}${buildQuery({
        organization_id: organizationId,
        limit,
      })}`,
    )
  },
}
