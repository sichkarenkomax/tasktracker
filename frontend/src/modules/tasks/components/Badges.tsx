import { useI18n } from '../../../core/i18n'
import type { Translate, TranslationKey } from '../../../core/i18n'
import { describeDueDate, formatDeadline } from '../../../core/format'
import { TASK_PRIORITIES, TASK_STATUSES } from '../types'
import type { TaskPriority, TaskStatus } from '../types'

/**
 * The vocabulary of a task: statuses, priorities and deadlines.
 *
 * One module owns the label of every value, so the list, the detail page and the
 * filters cannot drift apart, and so a translator sees each term exactly once
 * instead of three hardcoded spellings.
 */

export const STATUS_LABELS: Record<TaskStatus, TranslationKey> = {
  todo: 'status.todo',
  in_progress: 'status.in_progress',
  deferred: 'status.deferred',
  done: 'status.done',
}

export const PRIORITY_LABELS: Record<TaskPriority, TranslationKey> = {
  low: 'priority.low',
  medium: 'priority.medium',
  high: 'priority.high',
  urgent: 'priority.urgent',
}

export function useTaskVocabulary() {
  const { t } = useI18n()
  return {
    statusLabel: (status: TaskStatus) => t(STATUS_LABELS[status]),
    priorityLabel: (priority: TaskPriority) => t(PRIORITY_LABELS[priority]),
    statusOptions: TASK_STATUSES.map((value) => ({ value, label: t(STATUS_LABELS[value]) })),
    priorityOptions: TASK_PRIORITIES.map((value) => ({
      value,
      label: t(PRIORITY_LABELS[value]),
    })),
  }
}

export function StatusBadge({ status }: { status: TaskStatus }) {
  const { statusLabel } = useTaskVocabulary()
  return <span className={`badge badge--status-${status}`}>{statusLabel(status)}</span>
}

export function PriorityBadge({ priority }: { priority: TaskPriority }) {
  const { priorityLabel } = useTaskVocabulary()
  return <span className={`badge badge--priority-${priority}`}>{priorityLabel(priority)}</span>
}

/**
 * A deadline with a warning tint when it has passed on unfinished work, and the
 * relative form underneath so nobody has to do date arithmetic.
 */
export function DueDateBadge({
  value,
  isOverdue,
}: {
  value: string | null
  isOverdue: boolean
}) {
  const { locale, t } = useI18n()
  if (!value) return <span className="muted">{t('due.none')}</span>

  const relative = describeDueDate(value, t)
  return (
    <span className={isOverdue ? 'badge badge--overdue' : undefined}>
      {formatDeadline(value, locale)}
      {relative ? <span className="badge__hint"> ({relative})</span> : null}
    </span>
  )
}

export type { Translate, TranslationKey }
