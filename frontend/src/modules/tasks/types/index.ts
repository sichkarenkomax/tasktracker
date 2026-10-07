/**
 * Task shapes, mirroring `app/modules/tasks/schemas.py`.
 *
 * The enums are written out rather than derived from `string` so that a typo in a
 * comparison is a compile error instead of a filter that quietly returns the
 * wrong rows.
 */

export const TASK_STATUSES = ['todo', 'in_progress', 'deferred', 'done'] as const
export type TaskStatus = (typeof TASK_STATUSES)[number]

export const TASK_PRIORITIES = ['low', 'medium', 'high', 'urgent'] as const
export type TaskPriority = (typeof TASK_PRIORITIES)[number]

/** Units a planned duration can be counted in. */
export const DURATION_UNITS = ['minutes', 'hours', 'days', 'weeks', 'months'] as const
export type DurationUnit = (typeof DURATION_UNITS)[number]

/** How somebody is attached to a task beyond being responsible for it. */
export const PARTICIPANT_ROLES = ['co_assignee', 'watcher'] as const
export type ParticipantRole = (typeof PARTICIPANT_ROLES)[number]

export interface Task {
  id: string
  organization_id: string
  /** `null` means the task is not filed under a project - the inbox. */
  project_id: string | null
  title: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority
  /** Mandatory: a task always has somebody responsible for it. */
  assignee_id: string
  /** The reporter. Filled in at creation and not editable. */
  creator_id: string
  due_date: string | null
  completed_at: string | null
  planned_start: string | null
  planned_end: string | null
  planned_duration: number | null
  duration_unit: DurationUnit
  created_at: string
  updated_at: string
}

export interface TaskParticipant {
  task_id: string
  user_id: string
  role: ParticipantRole
  created_at: string
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
  planned_start?: string | null
  planned_end?: string | null
  planned_duration?: number | null
  duration_unit?: DurationUnit | null
  /** Only used by the flat `createUnfiled`; the project route takes it from the URL. */
  project_id?: string | null
}

/**
 * A partial task update.
 *
 * `due_date`, `description` and `project_id` are declared as `?: string | null`
 * rather than `?: string` on purpose: the API distinguishes "key omitted" from
 * "key set to null", and `JSON.stringify` drops undefined keys, so leaving a
 * field undefined clears nothing while passing null clears it. Getting this
 * backwards silently deletes a deadline or files a task back into the inbox.
 *
 * `assignee_id` is the one nullable field that may not be sent as null: a task
 * always has somebody responsible for it, and the API answers 422 rather than
 * accepting a task nobody owns.
 */
export interface TaskUpdate {
  title?: string
  description?: string | null
  priority?: TaskPriority | null
  due_date?: string | null
  assignee_id?: string | null
  status?: TaskStatus | null
  project_id?: string | null
  planned_start?: string | null
  planned_end?: string | null
  planned_duration?: number | null
  duration_unit?: DurationUnit | null
}

export interface TaskFilters {
  status?: TaskStatus[]
  priority?: TaskPriority[]
  project_id?: string
  assignee_id?: string
  /** Only tasks not filed under any project. */
  unfiled?: boolean
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

export type { TranslationKey } from '../../../core/i18n'
