import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { daysUntil, formatDateTime, plural } from '../../../core/format'
import { useAsync, useMutation } from '../../../core/hooks/useAsync'
import { useCapabilities } from '../../../core/permissions/capabilities'
import { organizationsApi } from '../../../core/organizations/api'
import type { Member } from '../../../core/organizations/api'
import { useOrganization } from '../../../core/organizations/OrganizationContext'
import { projectsApi } from '../../../core/projects/api'
import { activityApi, tasksApi } from '../api'
import { ActivityFeed } from '../components/ActivityFeed'
import {
  DueDateBadge,
  PRIORITY_OPTIONS,
  PriorityBadge,
  STATUS_OPTIONS,
  StatusBadge,
} from '../components/Badges'
import { CommentThread } from '../components/CommentThread'
import { TaskDateField } from '../components/TaskDateField'
import { TaskFieldSelect } from '../components/TaskFieldSelect'
import { isDone } from '../types'
import type { Comment, Task, TaskPriority, TaskStatus, TaskUpdate } from '../types'

const EMPTY_PAGE = { items: [] as Comment[], total: 0, limit: 0, offset: 0 }

/**
 * Task details (section 31): title, description, the four fields, then comments
 * and activity.
 *
 * Every field commits on its own, so a half-finished change to the title never
 * blocks fixing a deadline. Each mutation reloads from the server rather than
 * patching local state, because a PATCH can be refused by the role check or by a
 * business rule, and only the server's version is guaranteed to be true.
 */
export function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>()
  const navigate = useNavigate()
  const { current: organization } = useOrganization()
  const organizationId = organization?.id ?? null
  const capabilities = useCapabilities(organizationId)

  const task = useAsync(
    () =>
      organizationId && taskId
        ? tasksApi.get(organizationId, taskId)
        : Promise.resolve<Task | null>(null),
    [organizationId, taskId],
  )

  const project = useAsync(
    () =>
      organizationId && task.data
        ? projectsApi.get(task.data.project_id, organizationId)
        : Promise.resolve(null),
    [organizationId, task.data?.project_id],
  )

  const roster = useAsync(
    () =>
      organizationId
        ? organizationsApi.members(organizationId)
        : Promise.resolve([] as Member[]),
    [organizationId],
  )

  const comments = useAsync(
    () =>
      organizationId && taskId
        ? tasksApi.listComments(organizationId, taskId)
        : Promise.resolve(EMPTY_PAGE),
    [organizationId, taskId],
  )

  const activity = useAsync(
    () =>
      organizationId && taskId
        ? activityApi.forEntity(organizationId, 'task', taskId)
        : Promise.resolve({ items: [], total: 0, limit: 0, offset: 0 }),
    [organizationId, taskId],
  )

  const refreshAll = useCallback(() => {
    task.reload()
    comments.reload()
    activity.reload()
  }, [task, comments, activity])

  const patch = useMutation<TaskUpdate, void>(async (body) => {
    if (!organizationId || !taskId) return
    await tasksApi.update(organizationId, taskId, body)
    refreshAll()
  })

  /**
   * The fields edit through `patch.runOrThrow`, because each control restores its
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

  if (!organization) return <p className="notice">Loading...</p>

  if (task.error) {
    return (
      <section>
        <h1>Task</h1>
        <p className="notice notice--error">{task.error}</p>
        <p>
          <Link to="/projects">Back to projects</Link>
        </p>
      </section>
    )
  }

  if (!task.data) return <p className="notice">Loading task...</p>

  const current = task.data
  const overdue = !isDone(current.status) && (daysUntil(current.due_date) ?? 1) < 0
  const members = roster.data ?? []
  const rosterNames = new Map(members.map((member) => [member.user_id, member.first_name || member.username]))
  const commentCount = comments.data?.total ?? 0

  return (
    <section>
      <nav className="breadcrumb">
        <Link to="/projects">Projects</Link>
        <span aria-hidden="true"> / </span>
        {project.data ? (
          <Link to={`/projects/${current.project_id}/tasks`}>{project.data.name}</Link>
        ) : (
          <span>Project</span>
        )}
        <span aria-hidden="true"> / </span>
        <span>Task</span>
      </nav>

      <header className="page-header">
        <h1>
          <TaskTitleEditor
            value={current.title}
            disabled={!capabilities.canEditTask}
            onCommit={(title) => commitField({ title })}
          />
        </h1>
        <div className="badges">
          <StatusBadge status={current.status} />
          <PriorityBadge priority={current.priority} />
          <DueDateBadge value={current.due_date} isOverdue={overdue} />
        </div>
      </header>

      <section className="panel">
        <h2>Details</h2>
        <div className="fields">
          <TaskFieldSelect<TaskStatus>
            label="Status"
            value={current.status}
            options={STATUS_OPTIONS}
            emptyLabel=""
            disabled={!capabilities.canEditTask}
            onCommit={(next) => commitField({ status: next })}
          />
          <TaskFieldSelect<TaskPriority>
            label="Priority"
            value={current.priority}
            options={PRIORITY_OPTIONS}
            emptyLabel="Default"
            disabled={!capabilities.canEditTask}
            onCommit={(next) => commitField({ priority: next })}
          />
          <TaskFieldSelect<string>
            label="Assignee"
            value={current.assignee_id}
            options={members.map((member) => ({
              value: member.user_id,
              label: member.first_name || member.username,
            }))}
            emptyLabel="Unassigned"
            disabled={!capabilities.canEditTask}
            onCommit={(next) => commitField({ assignee_id: next })}
          />
          <TaskDateField
            label="Due date"
            value={current.due_date}
            disabled={!capabilities.canEditTask}
            onCommit={(next) => commitField({ due_date: next })}
          />
        </div>
        {patch.error ? (
          <p className="notice notice--error" role="alert">
            {patch.error}
          </p>
        ) : null}
        <dl className="meta">
          <dt>Created</dt>
          <dd>{formatDateTime(current.created_at)}</dd>
          <dt>Completed</dt>
          <dd>{current.completed_at ? formatDateTime(current.completed_at) : 'Not completed'}</dd>
        </dl>
      </section>

      <section className="panel">
        <h2>Description</h2>
        <DescriptionEditor
          value={current.description}
          disabled={!capabilities.canEditTask}
          onSave={(value) => commitField({ description: value })}
        />
      </section>

      <CommentThread
        comments={comments.data?.items ?? []}
        members={members}
        canComment={capabilities.canComment}
        canDelete={(comment) => comment.author_id === current.creator_id || capabilities.canDeleteTask}
        onAdd={(content) => addComment.runOrThrow(content)}
        onDelete={(comment) => removeComment.runOrThrow(comment)}
      />

      <section className="panel">
        <h2>Activity</h2>
        <ActivityFeed items={activity.data?.items ?? []} actorNames={rosterNames} />
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
              const warning = `Delete "${current.title}" and its ${plural(commentCount, 'comment')}?`
              if (window.confirm(warning)) void removeTask.run()
            }}
          >
            Delete task
          </button>
        </footer>
      ) : null}
    </section>
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
  const [draft, setDraft] = useState(value)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)

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
            setError('A task needs a title.')
            return
          }
          setError(null)
          setEditing(false)
          if (trimmed === value) return
          void onCommit(trimmed).catch((cause: unknown) => {
            // Stay open on a rejected title, so the new text is not lost.
            setDraft(trimmed)
            setEditing(true)
            setError(cause instanceof Error ? cause.message : 'Could not save')
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
  disabled,
  onSave,
}: {
  value: string | null
  disabled?: boolean
  onSave: (value: string | null) => Promise<void>
}) {
  const [draft, setDraft] = useState(value ?? '')
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  // A save that failed leaves the editor open with the text still there: closing
  // it would throw away the words the person just wrote.
  useEffect(() => {
    if (value !== null) setDraft(value)
  }, [value])

  if (disabled || !dirty) {
    return (
      <div>
        <p className={value ? 'description' : 'muted'}>{value || 'No description yet.'}</p>
        {!disabled ? (
          <button
            type="button"
            className="link"
            onClick={() => {
              setDraft(value ?? '')
              setError(null)
              setDirty(true)
            }}
          >
            {value ? 'Edit' : 'Add a description'}
          </button>
        ) : null}
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
          setError(cause instanceof Error ? cause.message : 'Could not save')
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
          {pending ? 'Saving...' : 'Save'}
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
          Cancel
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
