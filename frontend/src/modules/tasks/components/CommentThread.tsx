import { useState } from 'react'

import { formatDateTime } from '../../../core/format'
import { useMutation } from '../../../core/hooks/useAsync'
import { useI18n } from '../../../core/i18n'
import type { Member } from '../../../core/organizations/api'
import { Avatar } from '../../../core/users/Avatar'
import type { Comment } from '../types'

/**
 * The comment thread (section 31).
 *
 * Oldest first: a thread read top-down is a conversation, and the newest entry is
 * the one the reader cares about, so it sits at the bottom next to the input.
 */
export interface CommentThreadProps {
  comments: Comment[]
  members: Member[]
  canComment: boolean
  canDelete: (comment: Comment) => boolean
  onAdd: (content: string) => Promise<void>
  onDelete: (comment: Comment) => Promise<void>
}

/**
 * Who wrote it, as the roster knows them - the name and the face come from the
 * same row so the two can never disagree (an unknown author, such as a removed
 * member, falls back to the generic name and the letter it spells).
 */
function authorOf(members: Member[], id: string): { name: string; avatar: string | null } {
  const member = members.find((item) => item.user_id === id)
  if (!member) return { name: '', avatar: null }
  return { name: member.first_name || member.username, avatar: member.avatar_url }
}

export function CommentThread({
  comments,
  members,
  canComment,
  canDelete,
  onAdd,
  onDelete,
}: CommentThreadProps) {
  const { t } = useI18n()
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
      setError(t('comments.blank'))
      return
    }
    setError(null)
    const result = await adding.run(content)
    if (result !== null) setDraft('')
  }

  return (
    <section className="panel">
      <h2>
        {t('comments.title')}
        {comments.length > 0 ? <span className="muted"> ({comments.length})</span> : null}
      </h2>

      {comments.length === 0 ? (
        <p className="muted">{t('comments.empty')}</p>
      ) : (
        <ul className="comments">
          {comments.map((comment) => {
            const author = authorOf(members, comment.author_id)
            const name = author.name || t('activity.someone')
            return (
              <li key={comment.id} className="comment">
                <div className="comment__meta">
                  <Avatar src={author.avatar} name={name} size="sm" />
                  <strong>{name}</strong>
                  <time dateTime={comment.created_at}>{formatDateTime(comment.created_at)}</time>
                </div>
                <p className="comment__body">{comment.content}</p>
                {canDelete(comment) ? (
                  <button
                    type="button"
                    className="link"
                    disabled={removing.pending}
                    onClick={() => void removing.run(comment)}
                  >
                    {t('comments.delete')}
                  </button>
                ) : null}
              </li>
              )
            })}
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
            <span className="visually-hidden">{t('comments.placeholder')}</span>
            <textarea
              rows={3}
              maxLength={10_000}
              value={draft}
              placeholder={t('comments.placeholder')}
              onChange={(event) => setDraft(event.target.value)}
            />
          </label>
          <div>
            <button type="submit" className="button button--primary" disabled={adding.pending}>
              {adding.pending ? t('comments.posting') : t('comments.submit')}
            </button>
          </div>
          {error || adding.error ? (
            <p className="notice notice--error" role="alert">
              {error ?? adding.error}
            </p>
          ) : null}
        </form>
      ) : (
        <p className="muted">{t('comments.cannotComment')}</p>
      )}
    </section>
  )
}
