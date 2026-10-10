import { DateField } from '../../../core/ui/DateField'
import type { Member } from '../../../core/organizations/api'
import { Listbox } from '../../../core/ui/Listbox'
import { PersonSelect } from '../../../core/users/PersonSelect'
import { useFieldCommit } from './useFieldCommit'

/**
 * A labelled select for one task field.
 *
 * Edits are committed on change rather than on blur: there is no intermediate
 * state in a select worth previewing, and firing a PATCH per hover while somebody
 * tabs through the header would publish a `task.status_changed` per field they
 * merely passed over.
 */
export interface TaskFieldSelectProps<T extends string> {
  label: string
  value: T | null
  /**
   * `avatarUrl` is only ever passed for fields whose options are people (the
   * responsible person, stage 2.4); a status or a project omits the key and
   * gets no thumbnail.
   */
  options: ReadonlyArray<{ value: T; label: string; avatarUrl?: string | null }>
  /**
   * Text for the blank option, which also makes the field clearable.
   *
   * Omitted for fields that always have a value - status, priority, the
   * responsible person. Offering "nothing" there is not an option the API can
   * accept, so a blank choice is a control that silently does whatever it likes.
   */
  emptyLabel?: string
  disabled?: boolean
  onCommit: (next: T | null) => Promise<void>
}

export function TaskFieldSelect<T extends string>({
  label,
  value,
  options,
  emptyLabel,
  disabled,
  onCommit,
}: TaskFieldSelectProps<T>) {
  const { draft, error, pending, commit } = useFieldCommit(value, onCommit)

  return (
    <label className="field">
      <span>{label}</span>
      <Listbox<T>
        value={draft === '' ? null : (draft as T)}
        options={options}
        placeholder={emptyLabel}
        clearable={emptyLabel !== undefined}
        disabled={disabled || pending}
        invalid={error !== null}
        onChange={(next) => void commit(next ?? '')}
      />
      {error ? (
        <span className="field__error" role="alert">
          {error}
        </span>
      ) : null}
    </label>
  )
}

/**
 * The responsible person, as a labelled field on a task.
 *
 * `TaskFieldSelect` with people in it rather than a fourth copy of the same
 * editor: the roster, the avatar, the position under the name and the personal
 * "names only" preference all live in `PersonSelect`, and a field that showed a
 * different list from the one on the create form would be a bug report.
 */
export function PersonTaskFieldSelect({
  label,
  members,
  value,
  emptyLabel,
  disabled,
  onCommit,
}: {
  label: string
  members: ReadonlyArray<Member>
  value: string | null
  /** Text for the blank option, which also makes the field clearable. */
  emptyLabel?: string
  disabled?: boolean
  onCommit: (next: string | null) => Promise<void>
}) {
  const { draft, error, pending, commit } = useFieldCommit(value, onCommit)

  return (
    <label className="field">
      <span>{label}</span>
      <PersonSelect
        members={members}
        value={draft === '' ? null : draft}
        placeholder={emptyLabel}
        clearable={emptyLabel !== undefined}
        disabled={disabled || pending}
        onChange={(next) => void commit(next ?? '')}
      />
      {error ? (
        <span className="field__error" role="alert">
          {error}
        </span>
      ) : null}
    </label>
  )
}

/**
 * The deadline field.
 *
 * An instant, not a day: "hand it in by 18:00" is what a deadline usually means,
 * and a time that only the browser could show was a time the product could not
 * store or compare. The control is our own calendar rather than
 * `<input type="date">`, whose popup the browser paints itself and will not
 * colour (see `core/ui/DateField`).
 */
export function TaskDateField({
  label,
  value,
  disabled,
  onCommit,
}: {
  label: string
  value: string | null
  disabled?: boolean
  onCommit: (next: string | null) => Promise<void>
}) {
const { draft, error, pending, commit } = useFieldCommit(value, async (next) => {
    // An empty date input means "no deadline", which is null and not "".
    await onCommit(next)
  })

  return (
    <label className="field">
      <span>{label}</span>
      <DateField
        withTime
        // Picking a day without an hour means "by the end of it", which is what
        // a deadline means; the alternative, midnight, would silently mark the
        // task overdue from the moment it was written.
        timeDefault="end-of-day"
        value={draft === '' ? null : draft}
        disabled={disabled || pending}
        invalid={error !== null}
        onChange={(next) => void commit(next ?? '')}
      />
      {error ? (
        <span className="field__error" role="alert">
          {error}
        </span>
      ) : null}
    </label>
  )
}
