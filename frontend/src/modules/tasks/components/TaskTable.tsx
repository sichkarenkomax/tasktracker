import { useState } from 'react'
import { Link } from 'react-router-dom'

import { formatDateTime, isOverdue, plural } from '../../../core/format'
import { useI18n } from '../../../core/i18n'
import { Icon } from '../../../core/layout/Icon'
import type { Member } from '../../../core/organizations/api'
import type { Project } from '../../../core/projects/api'
import { ColumnSettingsPanel } from '../../../core/ui/ColumnSettingsPanel'
import { DueDateBadge, PriorityBadge, StatusBadge } from './Badges'
import { columnSet, saveTaskColumns, taskColumns } from './columns'
import type { ColumnId } from './columns'
import { isDone } from '../types'
import type { Task } from '../types'

/**
 * The task table (section 30 lists the columns: task, status, priority,
 * assignee, due date, updated).
 *
 * The column set and their order are the reader's, not ours: the same list is
 * read as "what is overdue" by one person and as "who is carrying what" by
 * another, and a fixed set of columns serves neither. The layout is per-browser,
 * because it is a reading preference rather than shared data - two people looking
 * at the same backlog rarely want identical columns.
 */
export interface TaskTableProps {
  tasks: Task[]
  members: Member[]
  projects: Project[]
  /** True on a project-scoped list, where the project column would be constant. */
  projectScoped: boolean
  onToggleDone: (task: Task) => void
}

function memberName(members: Member[], id: string | null, fallback: string): string {
  if (id === null) return fallback
  const member = members.find((item) => item.user_id === id)
  if (!member) return fallback
  return member.first_name || member.username
}

export function TaskTable({
  tasks,
  members,
  projects,
  projectScoped,
  onToggleDone,
}: TaskTableProps) {
  const { t } = useI18n()
  const set = columnSet(t)
  const [columns, setColumns] = useState<ColumnId[]>(() => taskColumns(t))
  const [configuring, setConfiguring] = useState(false)

  // A project-scoped list cannot usefully show the project, so it is dropped
  // rather than rendered as the same value on every row.
  const visible = columns.filter((id) => !(projectScoped && id === 'project'))
  const projectNames = new Map(projects.map((project) => [project.id, project.name]))

  function applyColumns(next: ColumnId[]) {
    setColumns(next)
    saveTaskColumns(t, next)
  }

  function cell(task: Task, column: ColumnId): React.ReactNode {
    const overdue = !isDone(task.status) && isOverdue(task.due_date)

    switch (column) {
      case 'title':
        return (
          <Link to={`/tasks/${task.id}`} className="cell-title">
            {task.title}
          </Link>
        )
      case 'status':
        return <StatusBadge status={task.status} />
      case 'priority':
        return <PriorityBadge priority={task.priority} />
      case 'assignee':
        return task.assignee_id ? (
          memberName(members, task.assignee_id, t('activity.someone'))
        ) : (
          <span className="muted">{t('tasks.unassigned')}</span>
        )
      case 'due_date':
        return <DueDateBadge value={task.due_date} isOverdue={overdue} />
      case 'project':
        return task.project_id ? (
          projectNames.get(task.project_id) ?? (
            <span className="muted">{t('tasks.unknownProject')}</span>
          )
        ) : (
          <span className="muted">{t('tasks.noProject')}</span>
        )
      case 'updated_at':
        return <span className="muted">{formatDateTime(task.updated_at)}</span>
      case 'created_at':
        return <span className="muted">{formatDateTime(task.created_at)}</span>
      default:
        return null
    }
  }

  if (tasks.length === 0) {
    return <p className="notice">{t('tasks.noTasks')}</p>
  }

  return (
    <>
      <div className="table-toolbar">
        <button
          type="button"
          className="button button--ghost"
          aria-expanded={configuring}
          onClick={() => setConfiguring((open) => !open)}
        >
          <Icon name="columns" size={15} />
          {t('columns.configure')}
        </button>
      </div>

      {configuring ? (
        <ColumnSettingsPanel set={set} columns={columns} onChange={applyColumns} />
      ) : null}

      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th scope="col" className="table__check">
                <span className="visually-hidden">{t('tasks.doneColumn')}</span>
              </th>
              {visible.map((column) => (
                <th key={column} scope="col">
                  {set.labels[column]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => {
              const overdue = !isDone(task.status) && isOverdue(task.due_date)
              return (
                <tr key={task.id} className={overdue ? 'table__row--overdue' : undefined}>
                  <td className="table__check">
                    <input
                      type="checkbox"
                      checked={isDone(task.status)}
                      aria-label={
                        isDone(task.status)
                          ? t('tasks.reopenAria', { title: task.title })
                          : t('tasks.completeAria', { title: task.title })
                      }
                      onChange={() => onToggleDone(task)}
                    />
                  </td>
                  {visible.map((column) => (
                    <td key={column}>{cell(task, column)}</td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
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
  const { t } = useI18n()
  if (total <= limit) return null

  const from = offset + 1
  const to = Math.min(offset + limit, total)
  const noun = plural(total, t('pagination.task'), t('pagination.tasks'))

  return (
    <nav className="pagination" aria-label={t('pagination.task')}>
      <button
        type="button"
        className="button button--ghost"
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - limit))}
      >
        {t('pagination.previous')}
      </button>
      <span className="muted">{t('pagination.showing', { from, to, total: noun })}</span>
      <button
        type="button"
        className="button button--ghost"
        disabled={offset + limit >= total}
        onClick={() => onChange(offset + limit)}
      >
        {t('pagination.next')}
      </button>
    </nav>
  )
}
