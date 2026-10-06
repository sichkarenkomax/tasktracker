import { Link } from 'react-router-dom'

import { daysUntil, EMPTY, formatDateTime, plural } from '../../../core/format'
import type { Member } from '../../../core/organizations/api'
import { DueDateBadge, PriorityBadge, StatusBadge } from './Badges'
import { isDone } from '../types'
import type { Task } from '../types'

/**
 * The task table (section 30 lists the columns: task, status, priority,
 * assignee, due date, updated).
 */
export interface TaskTableProps {
  tasks: Task[]
  members: Member[]
  projectScoped: boolean
  /** Project id to name, for the organization-wide list. */
  projectNames?: ReadonlyMap<string, string>
  onToggleDone: (task: Task) => void
}

function memberName(members: Member[], id: string | null): string {
  if (id === null) return EMPTY
  const member = members.find((item) => item.user_id === id)
  if (!member) return 'someone'
  return member.first_name || member.username
}

export function TaskTable({
  tasks,
  members,
  projectScoped,
  projectNames,
  onToggleDone,
}: TaskTableProps) {
  if (tasks.length === 0) {
    return (
      <p className="notice">
        No tasks match. Clear the filters, or create the first one.
      </p>
    )
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th scope="col">Done</th>
          <th scope="col">Task</th>
          <th scope="col">Status</th>
          <th scope="col">Priority</th>
          <th scope="col">Assignee</th>
          <th scope="col">Due</th>
          <th scope="col">Updated</th>
        </tr>
      </thead>
      <tbody>
        {tasks.map((task) => {
          const overdue = !isDone(task.status) && (daysUntil(task.due_date) ?? 1) < 0
          return (
            <tr key={task.id} className={overdue ? 'table__row--overdue' : undefined}>
              <td>
                <input
                  type="checkbox"
                  checked={isDone(task.status)}
                  aria-label={isDone(task.status) ? `Reopen ${task.title}` : `Complete ${task.title}`}
                  onChange={() => onToggleDone(task)}
                />
              </td>
              <td>
                <Link to={`/tasks/${task.id}`}>{task.title}</Link>
                {projectScoped ? null : (
                  <span className="muted">
                    {' '}
                    &middot; {projectNames?.get(task.project_id) ?? 'Unknown project'}
                  </span>
                )}
              </td>
              <td>
                <StatusBadge status={task.status} />
              </td>
              <td>
                <PriorityBadge priority={task.priority} />
              </td>
              <td>{task.assignee_id ? memberName(members, task.assignee_id) : <span className="muted">Unassigned</span>}</td>
              <td>
                <DueDateBadge value={task.due_date} isOverdue={overdue} />
              </td>
              <td className="muted">{formatDateTime(task.updated_at)}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

/** "Showing 1-25 of 130" plus prev/next, driven by the API's own `total`. */
export function TaskPagination({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number
  limit: number
  offset: number
  onChange: (offset: number) => void
}) {
  if (total <= limit) return null
  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + limit, total)
  return (
    <nav className="pagination" aria-label="Task pages">
      <button type="button" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
        Previous
      </button>
      <span>
        Showing {from}-{to} of {plural(total, 'task')}
      </span>
      <button
        type="button"
        disabled={offset + limit >= total}
        onClick={() => onChange(offset + limit)}
      >
        Next
      </button>
    </nav>
  )
}
