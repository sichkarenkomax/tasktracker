import { useState } from 'react'

import { useMutation } from '../../../core/hooks/useAsync'
import type { Member } from '../../../core/organizations/api'
import { PRIORITY_OPTIONS } from './Badges'
import type { TaskCreate, TaskPriority } from '../types'

/**
 * The inline "new task" form (section 30: the list has a create action).
 *
 * It lives above the table rather than behind a modal because adding a task is
 * the most frequent action in the product, and a dialog per task turns the daily
 * workflow into click, wait, type, confirm.
 */
export interface TaskCreateFormProps {
  members: Member[]
  disabled?: boolean
  onCreate: (input: TaskCreate) => Promise<void>
}

export function TaskCreateForm({ members, disabled, onCreate }: TaskCreateFormProps) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [priority, setPriority] = useState<TaskPriority | ''>('')
  const [dueDate, setDueDate] = useState('')
  const [assigneeId, setAssigneeId] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const mutation = useMutation<TaskCreate, void>(async (input) => {
    await onCreate(input)
  })

  if (disabled) {
    return <p className="muted">Your role cannot create tasks here.</p>
  }

  if (!open) {
    return (
      <button type="button" className="button button--primary" onClick={() => setOpen(true)}>
        New task
      </button>
    )
  }

  function reset() {
    setTitle('')
    setPriority('')
    setDueDate('')
    setAssigneeId('')
    setLocalError(null)
    setOpen(false)
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const trimmed = title.trim()
    if (!trimmed) {
      // The API rejects a blank title too, but saying so here saves a round trip
      // and keeps the message next to the field that caused it.
      setLocalError('A task needs a title.')
      return
    }
    setLocalError(null)
    // Every field the form shows is sent. A control that looks editable and is not
    // is worse than no control: the reader believes the priority was recorded and
    // only finds out from the list.
    const created = await mutation.run({
      title: trimmed,
      priority: priority === '' ? null : priority,
      due_date: dueDate === '' ? null : dueDate,
      assignee_id: assigneeId === '' ? null : assigneeId,
    })
    if (created !== null) reset()
  }

  return (
    <form className="create-form" onSubmit={submit}>
      <label className="create-form__title">
        <span className="visually-hidden">Task title</span>
        <input
          autoFocus
          value={title}
          maxLength={300}
          placeholder="What needs doing?"
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>

      <label>
        <span>Priority</span>
        <select
          value={priority}
          onChange={(event) => setPriority(event.target.value as TaskPriority | '')}
        >
          <option value="">Default (medium)</option>
          {PRIORITY_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label>
        <span>Due date</span>
        <input
          type="date"
          value={dueDate}
          onChange={(event) => setDueDate(event.target.value)}
        />
      </label>

      <label>
        <span>Assignee</span>
        <select value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)}>
          <option value="">Unassigned</option>
          {members.map((member) => (
            <option key={member.user_id} value={member.user_id}>
              {member.first_name || member.username}
            </option>
          ))}
        </select>
      </label>

      <div className="create-form__actions">
        <button type="submit" className="button button--primary" disabled={mutation.pending}>
          {mutation.pending ? 'Creating...' : 'Create'}
        </button>
        <button type="button" className="button" onClick={reset}>
          Cancel
        </button>
      </div>

      {localError || mutation.error ? (
        <p className="notice notice--error" role="alert">
          {localError ?? mutation.error}
        </p>
      ) : null}
    </form>
  )
}
