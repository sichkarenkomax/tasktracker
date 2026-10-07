import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { daysUntil, formatDateTime } from '../../../core/format'
import { useAsync, useMutation } from '../../../core/hooks/useAsync'
import { useI18n } from '../../../core/i18n'
import { Icon } from '../../../core/layout/Icon'
import { organizationsApi } from '../../../core/organizations/api'
import type { Member } from '../../../core/organizations/api'
import { useOrganization } from '../../../core/organizations/OrganizationContext'
import { RequiresOrganization } from '../../../core/organizations/RequiresOrganization'
import { useCapabilities } from '../../../core/permissions/capabilities'
import { projectsApi } from '../../../core/projects/api'
import type { Project } from '../../../core/projects/api'
import { activityApi, tasksApi } from '../api'
import { ActivityFeed } from '../components/ActivityFeed'
import {
  DueDateBadge,
  PriorityBadge,
  StatusBadge,
  useTaskVocabulary,
} from '../components/Badges'
import { CommentThread } from '../components/CommentThread'
import { ParticipantList } from '../components/ParticipantList'
import { PlanningFields } from '../components/PlanningFields'
import { TaskDateField, TaskFieldSelect } from '../components/TaskFieldSelect'
import { isDone } from '../types'
import type {
  Comment,
  ParticipantRole,
  Task,
  TaskParticipant,
  TaskPriority,
  TaskStatus,
  TaskUpdate,
} from '../types'

const EMPTY_PAGE = { items: [] as Comment[], total: 0, limit: 0, offset: 0 }

/**
 * Task details (section 31).
 *
 * Opens in a reading mode: every field shows its value and becomes editable when
 * clicked. Most visits are reading, and a form open on arrival turns "what is this
 * task" into "do I dare touch this". Somebody who does want to change several
 * things at once presses the edit button and gets the whole task as one form.
 *
 * Either way each field commits on its own, and every mutation reloads from the
 * server rather than patching local state, because a PATCH can be refused by the
 * role check or by a business rule and only the server's version is guaranteed to
 * be true.
 */
export function TaskDetailPage() {
  return (
    <RequiresOrganization>
      <TaskDetail />
    </RequiresOrganization>
  )
}

function TaskDetail() {
  const { t } = useI18n()
  const { taskId } = useParams<{ taskId: string }>()
  const navigate = useNavigate()
  const { current: organization } = useOrganization()
  const organizationId = organization?.id ?? null
  const capabilities = useCapabilities(organizationId)
  const { statusOptions, priorityOptions } = useTaskVocabulary()
  const [wholeTaskOpen, setWholeTaskOpen] = useState(false)

  const task = useAsync(
    () =>
      organizationId && taskId
        ? tasksApi.get(organizationId, taskId)
        : Promise.resolve<Task | null>(null),
    [organizationId, taskId],
  )

  const roster = useAsync(
    () => (organizationId ? organizationsApi.members(organizationId) : Promise.resolve([] as Member[])),
    [organizationId],
  )

  const projects = useAsync(
    () => (organizationId ? projectsApi.list(organizationId) : Promise.resolve([] as Project[])),
    [organizationId],
  )

  const comments = useAsync(
    () =>
      organizationId && taskId
        ? tasksApi.listComments(organizationId, taskId)
        : Promise.resolve(EMPTY_PAGE),
    [organizationId, taskId],
  )

  const participants = useAsync(
    () =>
      organizationId && taskId
        ? tasksApi.listParticipants(organizationId, taskId)
        : Promise.resolve([] as TaskParticipant[]),
    [organizationId, taskId],
  )

  const activity = useAsync(
    () =>
      organizationId && taskId
        ? activityApi.forEntity(organizationId, 'task', taskId)
        : Promise.resolve({ items: [], total: 0, limit: 0, offset: 0 }),
    [organizationId, taskId],
  )

  const patch = useMutation<TaskUpdate, void>(async (body) => {
    if (!organizationId || !taskId) return
    await tasksApi.update(organizationId, taskId, body)
    refreshAll()
  })

  const refreshAll = () => {
    task.reload()
    comments.reload()
    participants.reload()
    activity.reload()
  }

  /**
   * Fields commit through `runOrThrow` because each control restores its own
   * previous value when a save is refused: a rejected status change must not leave
   * the select claiming the task moved when it did not.
   */
  const commitField = (body: TaskUpdate) => patch.runOrThrow(body)

  const removeTask = useMutation<void, void>(async () => {
    if (!organizationId || !taskId) return
    await tasksApi.remove(organizationId, taskId)
    navigate('/projects')
  })

  const addComment = useMutation<string, void>(async (content) => {
    if (!organizationId || !taskId) return
    await tasksApi.addComment(organizationId, taskId, content)
    comments.reload()
    activity.reload()
  })

  const removeComment = useMutation<Comment, void>(async (comment) => {
    if (!organizationId || !taskId) return
    await tasksApi.removeComment(organizationId, taskId, comment.id)
    comments.reload()
    activity.reload()
  })

  const addParticipant = useMutation<
    { userId: string; role: ParticipantRole },
    void
  >(async ({ userId, role }) => {
    if (!organizationId || !taskId) return
    await tasksApi.addParticipant(organizationId, taskId, userId, role)
    participants.reload()
    activity.reload()
  })

  const removeParticipant = useMutation<
    { userId: string; role: ParticipantRole },
    void
  >(async ({ userId, role }) => {
    if (!organizationId || !taskId) return
    await tasksApi.removeParticipant(organizationId, taskId, userId, role)
    participants.reload()
    activity.reload()
  })

  if (!organizationId) return null

  if (task.error) {
    return (
      <section>
        <h1>{t('tasks.title')}</h1>
        <p className="notice notice--error">{task.error}</p>
        <p>
          <Link to="/projects">{t('projects.backToProjects')}</Link>
        </p>
      </section>
    )
  }

  if (!task.data) return <p className="notice">{t('app.loading')}</p>

  const current = task.data
  const overdue = !isDone(current.status) && (daysUntil(current.due_date) ?? 1) < 0
  const members = roster.data ?? []
  const projectList = projects.data ?? []
  const canEdit = capabilities.canEditTask
  const actorNames = new Map(
    members.map((member) => [member.user_id, member.first_name || member.username]),
  )

  return (
    <section className="narrow-wide">
      <header className="page-header">
        <button
          type="button"
          className="page-header__back"
          onClick={() =>
            navigate(current.project_id ? `/projects/${current.project_id}/tasks` : '/tasks')
          }
        >
          <Icon name="chevron" size={14} className="page-header__back-icon" />
          <span>{t('app.back')}</span>
        </button>
        <h1>
          <TaskTitleEditor
            value={current.title}
            disabled={!canEdit}
            onCommit={(title) => commitField({ title })}
          />
        </h1>
        <div className="page-header__actions">
          {canEdit ? (
            <button
              type="button"
              className={wholeTaskOpen ? 'button button--primary' : 'button button--ghost'}
              aria-pressed={wholeTaskOpen}
              onClick={() => setWholeTaskOpen((open) => !open)}
            >
              <Icon name={wholeTaskOpen ? 'check' : 'edit'} size={15} />
              {wholeTaskOpen ? t('tasks.doneEditing') : t('tasks.editTask')}
            </button>
          ) : null}
        </div>
      </header>

      <div className="badges">
        <StatusBadge status={current.status} />
        <PriorityBadge priority={current.priority} />
        <DueDateBadge value={current.due_date} isOverdue={overdue} />
      </div>

      {wholeTaskOpen ? (
        <section className="panel">
          <h2>{t('tasks.editing')}</h2>
          <div className="fields">
            <TaskFieldSelect<TaskStatus>
              label={t('tasks.status')}
              value={current.status}
              options={statusOptions}
              onCommit={(next) => commitField({ status: next })}
            />
            <TaskFieldSelect<TaskPriority>
              label={t('tasks.priority')}
              value={current.priority}
              options={priorityOptions}
              onCommit={(next) => commitField({ priority: next })}
            />
            <TaskFieldSelect<string>
              label={t('tasks.assignee')}
              value={current.assignee_id}
              options={members.map((member) => ({
                value: member.user_id,
                label: member.first_name || member.username,
              }))}
              // No empty option at all: a task always has somebody responsible,
              // and a blank choice is a value the API refuses rather than stores.
              onCommit={(next) => commitField({ assignee_id: next })}
            />
            <TaskDateField
              label={t('tasks.dueDate')}
              value={current.due_date}
              onCommit={(next) => commitField({ due_date: next })}
            />
            <TaskFieldSelect<string>
              label={t('columns.column.project')}
              value={current.project_id}
              options={projectList.map((project) => ({ value: project.id, label: project.name }))}
              emptyLabel={t('tasks.noProject')}
              onCommit={(next) => commitField({ project_id: next })}
            />
          </div>
          <DescriptionEditor
            value={current.description}
            onSave={(value) => commitField({ description: value })}
          />
        </section>
      ) : (
        <>
          <section className="panel">
            <h2>{t('tasks.details')}</h2>
            <p className="muted panel__hint">{t('tasks.readOnlyHint')}</p>
            <ReadOnlyFields
              task={current}
              members={members}
              projects={projectList}
              canEdit={canEdit}
              onCommit={commitField}
            />
            <dl className="meta">
              <dt>{t('app.createdAt')}</dt>
              <dd>{formatDateTime(current.created_at)}</dd>
              <dt>{t('app.completedAt')}</dt>
              <dd>
                {current.completed_at ? formatDateTime(current.completed_at) : t('tasks.notCompleted')}
              </dd>
            </dl>
          </section>

          <section className="panel">
            <h2>{t('tasks.description')}</h2>
            {canEdit ? (
              <DescriptionEditor
                value={current.description}
                onSave={(value) => commitField({ description: value })}
              />
            ) : (
              <p className={current.description ? 'description' : 'muted'}>
                {current.description || t('tasks.noDescription')}
              </p>
            )}
          </section>
        </>
      )}

      {patch.error ? (
        <p className="notice notice--error" role="alert">
          {patch.error}
        </p>
      ) : null}

      <section className="panel">
        <h2>
          <Icon name="calendar" size={15} /> {t('tasks.planning')}
        </h2>
        {current.planned_start || current.planned_duration !== null ? (
          <PlanningFields
            start={current.planned_start}
            end={current.planned_end}
            duration={current.planned_duration}
            unit={current.duration_unit}
            disabled={!canEdit}
            onCommit={commitField}
          />
        ) : (
          <>
            <p className="muted">{t('tasks.noPlan')}</p>
            {canEdit ? (
              <PlanningFields
                start={null}
                end={null}
                duration={null}
                unit={current.duration_unit}
                onCommit={commitField}
              />
            ) : null}
          </>
        )}
      </section>

      <section className="panel">
        <h2>{t('tasks.people')}</h2>
        <ParticipantList
          reporterId={current.creator_id}
          responsibleId={current.assignee_id}
          participants={participants.data ?? []}
          members={members}
          canEdit={canEdit}
          onAdd={(userId, role) => addParticipant.runOrThrow({ userId, role })}
          onRemove={(userId, role) => removeParticipant.runOrThrow({ userId, role })}
        />
        {addParticipant.error ? (
          <p className="notice notice--error" role="alert">
            {addParticipant.error}
          </p>
        ) : null}
        {removeParticipant.error ? (
          <p className="notice notice--error" role="alert">
            {removeParticipant.error}
          </p>
        ) : null}
      </section>

      <CommentThread
        comments={comments.data?.items ?? []}
        members={members}
        canComment={capabilities.canComment}
        canDelete={(comment) =>
          comment.author_id === current.creator_id || capabilities.canDeleteTask
        }
        onAdd={(content) => addComment.runOrThrow(content)}
        onDelete={(comment) => removeComment.runOrThrow(comment)}
      />

      <section className="panel">
        <h2>{t('activity.title')}</h2>
        <ActivityFeed items={activity.data?.items ?? []} actorNames={actorNames} />
      </section>

      {capabilities.canDeleteTask ? (
        <footer className="danger-zone">
          {removeTask.error ? (
            <p className="notice notice--error" role="alert">
              {removeTask.error}
            </p>
          ) : null}
          <button
            type="button"
            className="button button--danger"
            disabled={removeTask.pending}
            onClick={() => {
              const count = comments.data?.total ?? 0
              const warning = t('tasks.deleteTaskConfirm', {
                title: current.title,
                comments: `${count} ${count === 1 ? t('pagination.task') : t('pagination.tasks')}`,
              })
              if (window.confirm(warning)) void removeTask.run()
            }}
          >
            <Icon name="trash" size={15} />
            {t('tasks.deleteTask')}
          </button>
        </footer>
      ) : null}
    </section>
  )
}

/**
 * The reading view: values as text, a control as soon as the field is touched.
 *
 * The hover and focus outlines are the affordance - a field that looks like text
 * and turns into a select on click is the whole interaction, so it has to look
 * tappable on approach.
 */
function ReadOnlyFields({
  task,
  members,
  projects,
  canEdit,
  onCommit,
}: {
  task: Task
  members: Member[]
  projects: Project[]
  canEdit: boolean
  onCommit: (body: TaskUpdate) => Promise<void>
}) {
  const { t } = useI18n()
  const { statusLabel, priorityLabel, statusOptions, priorityOptions } = useTaskVocabulary()
  const [editing, setEditing] = useState<string | null>(null)

  const nameOf = (id: string): string => {
    const member = members.find((item) => item.user_id === id)
    return member ? member.first_name || member.username : t('activity.someone')
  }

  // The value is the button. A separate "edit" control next to every row would
  // put eight affordances on screen for a page most people only read, and the
  // dashed underline on the value says the same thing where the eye already is.
  const begin = (field: string) => () => {
    if (canEdit) setEditing(field)
  }

  /** The reading state of a field: text that opens its editor when pressed. */
  const read = (field: string, content: React.ReactNode) =>
    canEdit ? (
      <button type="button" className="readfields__value" onClick={begin(field)}>
        {content}
      </button>
    ) : (
      <span className="readfields__value readfields__value--static">{content}</span>
    )

  const memberOptions = members.map((member) => ({
    value: member.user_id,
    label: member.first_name || member.username,
  }))
  const projectOptions = projects.map((project) => ({ value: project.id, label: project.name }))

  return (
    <dl className="readfields">
      <ReadRow label={t('tasks.status')} editing={editing === 'status'} onStop={() => setEditing(null)}>
        {editing === 'status' ? (
          <TaskFieldSelect<TaskStatus>
            label={t('tasks.status')}
            value={task.status}
            options={statusOptions}
            onCommit={async (next) => {
              await onCommit({ status: next })
              setEditing(null)
            }}
          />
        ) : (
          read('status', statusLabel(task.status))
        )}
      </ReadRow>

      <ReadRow
        label={t('tasks.priority')}
        editing={editing === 'priority'}
        onStop={() => setEditing(null)}
      >
        {editing === 'priority' ? (
          <TaskFieldSelect<TaskPriority>
            label={t('tasks.priority')}
            value={task.priority}
            options={priorityOptions}
            onCommit={async (next) => {
              await onCommit({ priority: next })
              setEditing(null)
            }}
          />
        ) : (
          read('priority', priorityLabel(task.priority))
        )}
      </ReadRow>

      <ReadRow
        label={t('tasks.assignee')}
        editing={editing === 'assignee'}
        onStop={() => setEditing(null)}
      >
        {editing === 'assignee' ? (
          <TaskFieldSelect<string>
            label={t('tasks.assignee')}
            value={task.assignee_id}
            options={memberOptions}
            onCommit={async (next) => {
              await onCommit({ assignee_id: next })
              setEditing(null)
            }}
          />
        ) : (
          read('assignee', nameOf(task.assignee_id))
        )}
      </ReadRow>

      <ReadRow label={t('tasks.dueDate')} editing={editing === 'due'} onStop={() => setEditing(null)}>
        {editing === 'due' ? (
          <TaskDateField
            label={t('tasks.dueDate')}
            value={task.due_date}
            onCommit={async (next) => {
              await onCommit({ due_date: next })
              setEditing(null)
            }}
          />
        ) : (
          read(
            'due',
            task.due_date ? task.due_date : <span className="muted">{t('tasks.noDeadline')}</span>,
          )
        )}
      </ReadRow>

      <ReadRow
        label={t('columns.column.project')}
        editing={editing === 'project'}
        onStop={() => setEditing(null)}
      >
        {editing === 'project' ? (
          <TaskFieldSelect<string>
            label={t('columns.column.project')}
            value={task.project_id}
            options={projectOptions}
            emptyLabel={t('tasks.noProject')}
            onCommit={async (next) => {
              await onCommit({ project_id: next })
              setEditing(null)
            }}
          />
        ) : (
          read(
            'project',
            task.project_id
              ? (projects.find((project) => project.id === task.project_id)?.name ??
                t('tasks.unknownProject'))
              : t('tasks.noProject'),
          )
        )}
      </ReadRow>

      {!canEdit ? <p className="muted">{t('tasks.cannotEdit')}</p> : null}
    </dl>
  )
}

function ReadRow({
  label,
  editing,
  onStop,
  children,
}: {
  label: string
  editing: boolean
  onStop: () => void
  children: React.ReactNode
}) {
  return (
    <div className={editing ? 'readfields__row readfields__row--editing' : 'readfields__row'}>
      <dt className="readfields__label">
        {editing ? (
          <button type="button" className="link" onClick={onStop}>
            {label}
          </button>
        ) : (
          // Pressing the label is the affordance: the value looks like text, and
          // this is how a reader finds out it is editable at all.
          <span>{label}</span>
        )}
      </dt>
      <dd className="readfields__cell">{children}</dd>
    </div>
  )
}

function TaskTitleEditor({
  value,
  disabled,
  onCommit,
}: {
  value: string
  disabled?: boolean
  onCommit: (title: string) => Promise<void>
}) {
  const { t } = useI18n()
  const [draft, setDraft] = useState(value)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)

  useEffect(() => setDraft(value), [value])

  if (disabled || !editing) {
    return (
      <button
        type="button"
        className="title-button"
        disabled={disabled}
        onClick={() => setEditing(true)}
      >
        {value}
      </button>
    )
  }

  return (
    <span className="title-editor">
      <input
        autoFocus
        value={draft}
        maxLength={300}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            setDraft(value)
            setEditing(false)
          }
        }}
        onBlur={() => {
          const trimmed = draft.trim()
          if (!trimmed) {
            setError(t('tasks.titleRequired'))
            return
          }
          setError(null)
          setEditing(false)
          if (trimmed === value) return
          void onCommit(trimmed).catch((cause: unknown) => {
            // Stay open on a rejected title, so the new text is not lost.
            setDraft(trimmed)
            setEditing(true)
            setError(cause instanceof Error ? cause.message : t('error.generic'))
          })
        }}
      />
      {error ? (
        <span className="field__error" role="alert">
          {error}
        </span>
      ) : null}
    </span>
  )
}

function DescriptionEditor({
  value,
  onSave,
}: {
  value: string | null
  onSave: (value: string | null) => Promise<void>
}) {
  const { t } = useI18n()
  const [draft, setDraft] = useState(value ?? '')
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  // Keep in step with the server value rather than the previous one, so an edit
  // made elsewhere does not get overwritten by a stale draft.
  useEffect(() => setDraft(value ?? ''), [value])

  if (!dirty) {
    return (
      <div>
        <p className={value ? 'description' : 'muted'}>{value || t('tasks.noDescription')}</p>
        <button
          type="button"
          className="link"
          onClick={() => {
            setDraft(value ?? '')
            setError(null)
            setDirty(true)
          }}
        >
          {value ? t('app.edit') : t('tasks.addDescription')}
        </button>
      </div>
    )
  }

  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault()
        setPending(true)
        setError(null)
        try {
          await onSave(draft.trim() || null)
          setDirty(false)
        } catch (cause: unknown) {
          // Stay open: closing would throw away the words just written.
          setError(cause instanceof Error ? cause.message : t('error.generic'))
        } finally {
          setPending(false)
        }
      }}
    >
      <textarea
        autoFocus
        rows={6}
        maxLength={20_000}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
      />
      <div className="create-form__actions">
        <button type="submit" className="button button--primary" disabled={pending}>
          {pending ? t('app.saving') : t('app.save')}
        </button>
        <button
          type="button"
          className="button"
          disabled={pending}
          onClick={() => {
            setDraft(value ?? '')
            setError(null)
            setDirty(false)
          }}
        >
          {t('app.cancel')}
        </button>
      </div>
      {error ? (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  )
}
