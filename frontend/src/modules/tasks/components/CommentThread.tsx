import { useState } from 'react'

import { formatDateTime, plural } from '../../../core/format'
import { useMutation } from '../../../core/hooks/useAsync'
import type { Member } from '../../../core/organizations/api'
import type { Comment } from '../types'

/**
 * The comment thread (section 31).
 *
 * Oldest first: a thread read top-down is a conversation, and the newest entry
 * is the one the reader cares about, so it sits at the bottom where the input
 * box is.
 */
export interface CommentThreadProps {
  comments: Comment[]
  members: Member[]
  canComment: boolean
  canDelete: (comment: Comment) => boolean
  onAdd: (content: string) => Promise<void>
  onDelete: (comment: Comment) => Promise<void>
}

function authorName(members: Member[], id: string): string {
  const member = members.find((item) => item.user_id === id)
  return member ? member.first_name || member.username : 'Someone'
}

export function CommentThread({
  comments,
  members,
  canComment,
  canDelete,
  onAdd,
  onDelete,
}: CommentThreadProps) {
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const adding = useMutation<string, void>(async (content) => {
    await onAdd(content)
  })
  const removing = useMutation<Comment, void>(async (comment) => {
    await onDelete(comment)
  })

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const content = draft.trim()
    if (!content) {
      setError('Write something first.')
      return
    }
    setError(null)
    const result = await adding.run(content)
    if (result !== null) setDraft('')
  }

  return (
    <section className="panel">
      <h2>
        Comments {comments.length > 0 ? <span className="muted">({comments.length})</span> : null}
      </h2>

      {comments.length === 0 ? (
        <p className="muted">No comments yet.</p>
      ) : (
        <ul className="comments">
          {comments.map((comment) => (
            <li key={comment.id} className="comment">
              <div className="comment__meta">
                <strong>{authorName(members, comment.author_id)}</strong>
                <time dateTime={comment.created_at}>{formatDateTime(comment.created_at)}</time>
              </div>
              <p className="comment__body">{comment.content}</p>
              {canDelete(comment) ? (
                <button
                  type="button"
                  className="link"
                  onClick={() => void removing.run(comment)}
                  disabled={removing.pending}
                >
                  Delete
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {removing.error ? (
        <p className="notice notice--error" role="alert">
          {removing.error}
        </p>
      ) : null}

      {canComment ? (
        <form className="comment-form" onSubmit={submit}>
          <label>
            <span className="visually-hidden">New comment</span>
            <textarea
              rows={3}
              maxLength={10_000}
              value={draft}
              placeholder="Leave a comment"
              onChange={(event) => setDraft(event.target.value)}
            />
          </label>
          <div>
            <button type="submit" className="button button--primary" disabled={adding.pending}>
              {adding.pending ? 'Posting...' : 'Comment'}
            </button>
            {draft.length > 0 ? (
              <span className="muted"> {plural(draft.trim().length, 'character')} typed</span>
            ) : null}
          </div>
          {error || adding.error ? (
            <p className="notice notice--error" role="alert">
              {error ?? adding.error}
            </p>
          ) : null}
        </form>
      ) : (
        <p className="muted">Your role cannot comment on this task.</p>
      )}
    </section>
  )
}
