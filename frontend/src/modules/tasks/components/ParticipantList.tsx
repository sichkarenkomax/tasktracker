import { useState } from 'react'

import { useMutation } from '../../../core/hooks/useAsync'
import { useI18n } from '../../../core/i18n'
import { Icon } from '../../../core/layout/Icon'
import type { Member } from '../../../core/organizations/api'
import { Avatar } from '../../../core/users/Avatar'
import { Listbox } from '../../../core/ui/Listbox'
import type { ParticipantRole, TaskParticipant } from '../types'

/**
 * Who is on this task.
 *
 * Three groups and only two of them are editable. The reporter is the creator,
 * filled in when the task was written down, and is shown rather than offered as a
 * choice: a report is a fact about the past, not a decision to make now.
 */
export function ParticipantList({
  reporterId,
  responsibleId,
  participants,
  members,
  canEdit,
  onAdd,
  onRemove,
}: {
  reporterId: string
  responsibleId: string
  participants: TaskParticipant[]
  members: Member[]
  canEdit: boolean
  onAdd: (userId: string, role: ParticipantRole) => Promise<void>
  onRemove: (userId: string, role: ParticipantRole) => Promise<void>
}) {
  const { t } = useI18n()
  const [picking, setPicking] = useState<ParticipantRole | null>(null)
  // Controlled rather than read off the form element: the picker is a button
  // now, and the choice has to survive re-renders of the row it sits in.
  const [who, setWho] = useState('')

  const adding = useMutation<{ userId: string; role: ParticipantRole }, void>(async (input) => {
    await onAdd(input.userId, input.role)
  })
  const removing = useMutation<TaskParticipant, void>(async (participant) => {
    await onRemove(participant.user_id, participant.role)
  })

  const nameOf = (id: string): string => {
    const member = members.find((item) => item.user_id === id)
    return member ? member.first_name || member.username : t('activity.someone')
  }

  const avatarOf = (id: string): string | null =>
    members.find((item) => item.user_id === id)?.avatar_url ?? null

  // Name and face in one wrapper: the row is a space-between flex, and a bare
  // avatar plus a bare name would be pushed to opposite ends of it.
  const whoRow = (id: string) => (
    <span className="participants__who">
      <Avatar src={avatarOf(id)} name={nameOf(id)} size="sm" />
      {nameOf(id)}
    </span>
  )

  const rowsFor = (role: ParticipantRole) =>
    participants
      .filter((participant) => participant.role === role)
      .sort((a, b) => nameOf(a.user_id).localeCompare(nameOf(b.user_id)))

  // The reporter and the responsible person are already on the task; offering them
  // again would be a second, contradictory answer to the same question.
  const candidates = members.filter(
    (member) =>
      member.user_id !== reporterId &&
      member.user_id !== responsibleId &&
      !participants.some((participant) => participant.user_id === member.user_id),
  )

  function group(
    role: ParticipantRole,
    title: string,
    icon: 'user' | 'eye',
  ) {
    const rows = rowsFor(role)
    return (
      <div className="participants__group" key={role}>
        <div className="participants__head">
          <Icon name={icon} size={15} />
          <span>{title}</span>
          {canEdit ? (
            <button
              type="button"
              className="icon-button"
              aria-label={`${t('members.add')}: ${title}`}
              onClick={() => {
                setPicking((current) => (current === role ? null : role))
                // Every opening starts from "no choice yet".
                setWho('')
              }}
            >
              <Icon name="plus" size={14} />
            </button>
          ) : null}
        </div>

        {rows.length === 0 && picking !== role ? (
          <p className="muted participants__empty">{t('tasks.nobodyHere')}</p>
        ) : null}

        <ul className="participants__list">
          {rows.map((participant) => (
            <li key={`${participant.role}-${participant.user_id}`}>
              {whoRow(participant.user_id)}
              {canEdit ? (
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`${t('members.remove')}: ${nameOf(participant.user_id)}`}
                  disabled={removing.pending}
                  onClick={() => void removing.run(participant)}
                >
                  <Icon name="close" size={13} />
                </button>
              ) : null}
            </li>
          ))}
        </ul>

        {picking === role ? (
          <form
            className="participants__add"
            onSubmit={async (event) => {
              event.preventDefault()
              if (!who) return
              const done = await adding.run({ userId: who, role })
              if (done !== null) {
                setWho('')
                setPicking(null)
              }
            }}
          >
            <label>
              <span className="visually-hidden">{title}</span>
              <Listbox<string>
                value={who === '' ? null : who}
                options={candidates.map((member) => ({
                  value: member.user_id,
                  label: member.first_name || member.username,
                  avatarUrl: member.avatar_url,
                }))}
                placeholder={t('tasks.anyone')}
                onChange={(next) => setWho(next ?? '')}
              />
            </label>
            {/* The browser's `required` went with the native select, so the
                submit button itself holds the line until a person is chosen. */}
            <button
              type="submit"
              className="button button--primary"
              disabled={adding.pending || !who}
            >
              {t('app.create')}
            </button>
            <button
              type="button"
              className="link"
              onClick={() => {
                setWho('')
                setPicking(null)
              }}
            >
              {t('app.cancel')}
            </button>
            {adding.error ? (
              <span className="field__error" role="alert">
                {adding.error}
              </span>
            ) : null}
          </form>
        ) : null}
      </div>
    )
  }

  return (
    <div className="participants">
      <div className="participants__group">
        <div className="participants__head">
          <Icon name="user" size={15} />
          <span>{t('tasks.reporter')}</span>
        </div>
        <ul className="participants__list">
          <li>{whoRow(reporterId)}</li>
        </ul>
      </div>

      <div className="participants__group">
        <div className="participants__head">
          <Icon name="check" size={15} />
          <span>{t('tasks.responsible')}</span>
        </div>
        <ul className="participants__list">
          <li>{whoRow(responsibleId)}</li>
        </ul>
      </div>

      {group('co_assignee', t('tasks.coAssignees'), 'user')}
      {group('watcher', t('tasks.watchers'), 'eye')}

      {removing.error ? (
        <p className="notice notice--error" role="alert">
          {removing.error}
        </p>
      ) : null}
    </div>
  )
}
