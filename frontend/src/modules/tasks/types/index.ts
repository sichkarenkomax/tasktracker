/**
 * Task shapes, mirroring `app/modules/tasks/schemas.py`.
 *
 * The enums are written out rather than derived from `string` so that a typo in a
 * comparison is a compile error instead of a filter that quietly returns the
 * wrong rows.
 */

export const TASK_STATUSES = ['todo', 'in_progress', 'done'] as const
export type TaskStatus = (typeof TASK_STATUSES)[number]

export const TASK_PRIORITIES = ['low', 'medium', 'high', 'urgent'] as const
export type TaskPriority = (typeof TASK_PRIORITIES)[number]

export interface Task {
  id: string
  organization_id: string
  project_id: string
  title: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority
  assignee_id: string | null
  creator_id: string
  due_date: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export interface TaskPage {
  items: Task[]
  total: number
  limit: number
  offset: number
  sort: string
  direction: 'asc' | 'desc'
}

export interface Comment {
  id: string
  task_id: string
  author_id: string
  content: string
  created_at: string
  updated_at: string
}

export interface CommentPage {
  items: Comment[]
  total: number
  limit: number
  offset: number
}

export interface ActivityItem {
  id: string
  organization_id: string
  actor_id: string | null
  action: string
  entity_type: string | null
  entity_id: string | null
  summary: string | null
  created_at: string
}

export interface ActivityPage {
  items: ActivityItem[]
  total: number
  limit: number
  offset: number
}

export interface TaskCreate {
  title: string
  description?: string | null
  priority?: TaskPriority | null
  due_date?: string | null
  assignee_id?: string | null
}

/**
 * A partial task update.
 *
 * `due_date` and `description` are declared as `?: string | null` rather than
 * `?: string` on purpose: the API distinguishes "key omitted" from "key set to
 * null" (section 13), and `JSON.stringify` drops undefined keys, so leaving a
 * field undefined clears nothing while passing null clears it. Getting this
 * backwards silently deletes a deadline.
 */
export interface TaskUpdate {
  title?: string
  description?: string | null
  priority?: TaskPriority | null
  due_date?: string | null
  assignee_id?: string | null
  status?: TaskStatus | null
}

export interface TaskFilters {
  status?: TaskStatus[]
  priority?: TaskPriority[]
  assignee_id?: string
  unassigned?: boolean
  overdue?: boolean
  search?: string
  sort?: string
  direction?: 'asc' | 'desc'
  limit?: number
  offset?: number
}

/** Statuses that close a task; used for the "done" affordances in the UI. */
export const TERMINAL_STATUSES: readonly TaskStatus[] = ['done']

export function isDone(status: TaskStatus): boolean {
  return TERMINAL_STATUSES.includes(status)
}
