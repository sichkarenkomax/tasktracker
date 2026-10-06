import { useState } from 'react'

import { useI18n } from '../../../core/i18n'
import { useMutation } from '../../../core/hooks/useAsync'
import { Icon } from '../../../core/layout/Icon'
import type { Member } from '../../../core/organizations/api'
import type { Project } from '../../../core/projects/api'
import { useTaskVocabulary } from './Badges'
import type { TaskCreate, TaskPriority } from '../types'

/**
 * The inline "new task" form (section 30: the list has a create action).
 *
 * It lives above the table rather than behind a modal because adding a task is
 * the most frequent action in the product, and a dialog per task turns the daily
 * workflow into click, wait, type, confirm.
 *
 * Everything the form shows is sent. A control that looks editable and is not is
 * worse than no control: the reader believes the priority was recorded and only
 * finds out from the list.
 */
export interface TaskCreateFormProps {
  members: Member[]
  projects: Project[]
  /** Fixed on a project-scoped list; absent on the organization-wide one. */
  projectId?: string
  disabled?: boolean
  onCreate: (input: TaskCreate) => Promise<void>
}

export function TaskCreateForm({
  members,
  projects,
  projectId,
  disabled,
  onCreate,
}: TaskCreateFormProps) {
  const { t } = useI18n()
  const { priorityOptions } = useTaskVocabulary()
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState<TaskPriority | ''>('')
  const [dueDate, setDueDate] = useState('')
  const [assigneeId, setAssigneeId] = useState('')
  const [targetProject, setTargetProject] = useState(projectId ?? '')
  const [localError, setLocalError] = useState<string | null>(null)
  const mutation = useMutation<TaskCreate, void>(async (input) => {
    await onCreate(input)
  })

  if (disabled) {
    return <p className="muted">{t('tasks.cannotCreate')}</p>
  }

  function reset() {
    setTitle('')
    setDescription('')
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
      setLocalError(t('tasks.titleRequired'))
      return
    }
    setLocalError(null)
    const created = await mutation.run({
      title: trimmed,
      // An empty textarea means "no description", which is a value the API
      // understands; sending "" would store an empty string instead of NULL.
      description: description.trim() || null,
      priority: priority === '' ? null : priority,
      due_date: dueDate === '' ? null : dueDate,
      assignee_id: assigneeId === '' ? null : assigneeId,
      ...(projectId ? {} : { project_id: targetProject === '' ? null : targetProject }),
    })
    if (created !== null) reset()
  }

  if (!open) {
    return (
      <button type="button" className="button button--primary" onClick={() => setOpen(true)}>
        <Icon name="plus" size={15} />
        {t('tasks.newTask')}
      </button>
    )
  }

  return (
    <form className="create-form" onSubmit={submit}>
      <div className="create-form__grid">
        <label className="create-form__title">
          <span>{t('tasks.title')}</span>
          <input
            autoFocus
            value={title}
            maxLength={300}
            placeholder={t('tasks.titlePlaceholder')}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>

        {/* The description is editable right here rather than only afterwards:
            a person who writes it here has not had to decide, then change their
            mind, then remember to come back. */}
        <label className="create-form__description">
          <span>{t('tasks.description')}</span>
          <textarea
            rows={2}
            maxLength={20_000}
            value={description}
            placeholder={t('tasks.noDescription')}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>

        <label>
          <span>{t('tasks.priority')}</span>
          <select
            value={priority}
            onChange={(event) => setPriority(event.target.value as TaskPriority | '')}
          >
            <option value="">{t('priority.medium')}</option>
            {priorityOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>{t('tasks.dueDate')}</span>
          <input
            type="date"
            value={dueDate}
            onChange={(event) => setDueDate(event.target.value)}
          />
        </label>

        <label>
          <span>{t('tasks.assignee')}</span>
          <select value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)}>
            <option value="">{t('tasks.unassigned')}</option>
            {members.map((member) => (
              <option key={member.user_id} value={member.user_id}>
                {member.first_name || member.username}
              </option>
            ))}
          </select>
        </label>

        {projectId ? null : (
          <label>
            <span>{t('columns.column.project')}</span>
            <select
              value={targetProject}
              onChange={(event) => setTargetProject(event.target.value)}
            >
              <option value="">{t('tasks.noProject')}</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="create-form__actions">
        <button type="submit" className="button button--primary" disabled={mutation.pending}>
          {mutation.pending ? t('app.loading') : t('tasks.createTask')}
        </button>
        <button type="button" className="button" onClick={reset}>
          {t('app.cancel')}
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
