import { useEffect, useState } from 'react'

import { DateField } from '../../../core/ui/DateField'
import { Listbox } from '../../../core/ui/Listbox'

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
  const [draft, setDraft] = useState(value ?? '')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  // Re-sync when the server value changes underneath us - for example after a
  // reload picked up somebody else's edit. Without this the select would keep
  // showing the stale choice the user abandoned.
  useEffect(() => {
    setDraft(value ?? '')
  }, [value])

  async function commit(next: string) {
    setDraft(next)
    const parsed = (next || null) as T | null
    if (parsed === value) return

    setPending(true)
    setError(null)
    try {
      await onCommit(parsed)
    } catch (cause: unknown) {
      // Put the old value back: leaving the control showing something the server
      // rejected is how a UI starts lying about the state of the data.
      setDraft(value ?? '')
      setError(cause instanceof Error ? cause.message : 'Could not save')
    } finally {
      setPending(false)
    }
  }

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
  const [draft, setDraft] = useState(value ?? '')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    setDraft(value ?? '')
  }, [value])

  async function commit(next: string) {
    setDraft(next)
    // An empty date input means "no deadline", which is null and not "".
    const parsed = next === '' ? null : next
    if (parsed === value) return

    setPending(true)
    setError(null)
    try {
      await onCommit(parsed)
    } catch (cause: unknown) {
      setDraft(value ?? '')
      setError(cause instanceof Error ? cause.message : 'Could not save')
    } finally {
      setPending(false)
    }
  }

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
