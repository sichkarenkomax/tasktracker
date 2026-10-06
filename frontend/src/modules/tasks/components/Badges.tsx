import { describeDueDate } from '../../../core/format'
import { TASK_PRIORITIES, TASK_STATUSES } from '../types'
import type { TaskPriority, TaskStatus } from '../types'

/**
 * Small vocabulary components.
 *
 * Status and priority are rendered the same way in the list, in the detail page
 * and in the editor, so the label and the modifier class live together here -
 * otherwise a third view invents its own spelling and the colours drift.
 */

const STATUS_LABELS: Record<TaskStatus, string> = {
  todo: 'To do',
  in_progress: 'In progress',
  done: 'Done',
}

const PRIORITY_LABELS: Record<TaskPriority, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  urgent: 'Urgent',
}

export function StatusBadge({ status }: { status: TaskStatus }) {
  return <span className={`badge badge--status-${status}`}>{STATUS_LABELS[status]}</span>
}

export function PriorityBadge({ priority }: { priority: TaskPriority }) {
  return <span className={`badge badge--priority-${priority}`}>{PRIORITY_LABELS[priority]}</span>
}

/** A deadline with a warning tint when it has passed on unfinished work. */
export function DueDateBadge({
  value,
  isOverdue,
}: {
  value: string | null
  isOverdue: boolean
}) {
  if (!value) return <span className="muted">no deadline</span>
  const relative = describeDueDate(value)
  return (
    <span className={isOverdue ? 'badge badge--overdue' : undefined}>
      {value}
      {relative ? <span className="badge__hint"> ({relative})</span> : null}
    </span>
  )
}

export const STATUS_OPTIONS = TASK_STATUSES.map((value) => ({ value, label: STATUS_LABELS[value] }))

export const PRIORITY_OPTIONS = TASK_PRIORITIES.map((value) => ({
  value,
  label: PRIORITY_LABELS[value],
}))

export function statusLabel(status: TaskStatus): string {
  return STATUS_LABELS[status]
}

export function priorityLabel(priority: TaskPriority): string {
  return PRIORITY_LABELS[priority]
}
