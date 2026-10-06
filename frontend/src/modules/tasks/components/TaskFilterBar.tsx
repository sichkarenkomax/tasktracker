import { useEffect, useState } from 'react'

import type { Member } from '../../../core/organizations/api'
import { PRIORITY_OPTIONS, STATUS_OPTIONS } from './Badges'
import { TASK_PRIORITIES, TASK_STATUSES } from '../types'
import type { TaskFilters, TaskPriority, TaskStatus } from '../types'

/**
 * The filter bar above the task list (section 30 asks for search, filtering,
 * sorting and grouping).
 *
 * Filters live in the URL rather than in component state: a filtered view is
 * something people paste to a colleague, and it has to survive a reload and the
 * back button. The parent owns the values; this component only edits them.
 */
export interface TaskFilterBarProps {
  value: TaskFilters
  members: Member[]
  onChange: (next: TaskFilters) => void
}

const SORTABLE = [
  { value: 'created_at', label: 'Created' },
  { value: 'updated_at', label: 'Updated' },
  { value: 'due_date', label: 'Due date' },
  { value: 'title', label: 'Title' },
  { value: 'priority', label: 'Priority' },
  { value: 'status', label: 'Status' },
] as const

export function TaskFilterBar({ value, members, onChange }: TaskFilterBarProps) {
  // The text box is local state so that typing does not fire a request per
  // keystroke; the value is committed on submit or after a pause.
  const [term, setTerm] = useState(value.search ?? '')

  useEffect(() => {
    setTerm(value.search ?? '')
  }, [value.search])

  function toggleStatus(status: TaskStatus) {
    const current = value.status ?? []
    const next = current.includes(status)
      ? current.filter((item) => item !== status)
      : [...current, status]
    onChange({ ...value, status: next })
  }

  function togglePriority(priority: TaskPriority) {
    const current = value.priority ?? []
    const next = current.includes(priority)
      ? current.filter((item) => item !== priority)
      : [...current, priority]
    onChange({ ...value, priority: next })
  }

  const selectedStatuses = value.status ?? []
  const selectedPriorities = value.priority ?? []

  return (
    <form
      className="filters"
      role="search"
      onSubmit={(event) => {
        event.preventDefault()
        onChange({ ...value, search: term.trim() || undefined })
      }}
    >
      <label className="filters__search">
        <span className="visually-hidden">Search tasks</span>
        <input
          type="search"
          value={term}
          placeholder="Search title or description"
          onChange={(event) => setTerm(event.target.value)}
          onBlur={() => onChange({ ...value, search: term.trim() || undefined })}
        />
      </label>

      <fieldset className="filters__group">
        <legend>Status</legend>
        {STATUS_OPTIONS.map((option) => (
          <label key={option.value} className="chip">
            <input
              type="checkbox"
              checked={selectedStatuses.includes(option.value)}
              onChange={() => toggleStatus(option.value)}
            />
            {option.label}
          </label>
        ))}
      </fieldset>

      <fieldset className="filters__group">
        <legend>Priority</legend>
        {PRIORITY_OPTIONS.map((option) => (
          <label key={option.value} className="chip">
            <input
              type="checkbox"
              checked={selectedPriorities.includes(option.value)}
              onChange={() => togglePriority(option.value)}
            />
            {option.label}
          </label>
        ))}
      </fieldset>

      <label className="chip">
        <input
          type="checkbox"
          checked={value.unassigned ?? false}
          onChange={(event) => onChange({ ...value, unassigned: event.target.checked || undefined })}
        />
        Unassigned
      </label>

      <label className="chip">
        <input
          type="checkbox"
          checked={value.overdue ?? false}
          onChange={(event) => onChange({ ...value, overdue: event.target.checked || undefined })}
        />
        Overdue
      </label>

      <label>
        <span>Assignee</span>
        <select
          value={value.assignee_id ?? ''}
          onChange={(event) =>
            onChange({ ...value, assignee_id: event.target.value || undefined })
          }
        >
          <option value="">Anyone</option>
          {members.map((member) => (
            <option key={member.user_id} value={member.user_id}>
              {member.first_name || member.username}
            </option>
          ))}
        </select>
      </label>

      <label>
        <span>Sort by</span>
        <select
          value={value.sort ?? 'created_at'}
          onChange={(event) => onChange({ ...value, sort: event.target.value })}
        >
          {SORTABLE.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label>
        <span>Direction</span>
        <select
          value={value.direction ?? 'desc'}
          onChange={(event) =>
            onChange({ ...value, direction: event.target.value === 'asc' ? 'asc' : 'desc' })
          }
        >
          <option value="desc">Descending</option>
          <option value="asc">Ascending</option>
        </select>
      </label>

      <button type="button" className="link" onClick={() => onChange({ sort: 'created_at' })}>
        Reset
      </button>
    </form>
  )
}

/** Parse the filter part of a query string into the API's filter object. */
export function filtersFromSearch(search: string): TaskFilters {
  const params = new URLSearchParams(search)
  const statuses = params.getAll('status').filter((item): item is TaskStatus =>
    (TASK_STATUSES as readonly string[]).includes(item),
  )
  const priorities = params.getAll('priority').filter((item): item is TaskPriority =>
    (TASK_PRIORITIES as readonly string[]).includes(item),
  )
  const direction = params.get('direction')
  return {
    search: params.get('search') ?? undefined,
    status: statuses.length ? statuses : undefined,
    priority: priorities.length ? priorities : undefined,
    assignee_id: params.get('assignee') ?? undefined,
    unassigned: params.get('unassigned') === '1' || undefined,
    overdue: params.get('overdue') === '1' || undefined,
    sort: params.get('sort') ?? 'created_at',
    direction: direction === 'asc' ? 'asc' : 'desc',
  }
}

/** The inverse of `filtersFromSearch`, so the URL is the single source of truth. */
export function filtersToSearch(filters: TaskFilters): string {
  const params = new URLSearchParams()
  if (filters.search) params.set('search', filters.search)
  for (const status of filters.status ?? []) params.append('status', status)
  for (const priority of filters.priority ?? []) params.append('priority', priority)
  if (filters.assignee_id) params.set('assignee', filters.assignee_id)
  if (filters.unassigned) params.set('unassigned', '1')
  if (filters.overdue) params.set('overdue', '1')
  if (filters.sort && filters.sort !== 'created_at') params.set('sort', filters.sort)
  if (filters.direction === 'asc') params.set('direction', 'asc')
  const encoded = params.toString()
  return encoded ? `?${encoded}` : ''
}
