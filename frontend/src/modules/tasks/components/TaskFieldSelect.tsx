import { useEffect, useState } from 'react'

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
  options: ReadonlyArray<{ value: T; label: string }>
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
      <select
        value={draft}
        disabled={disabled || pending}
        onChange={(event) => void commit(event.target.value)}
      >
        {emptyLabel === undefined ? null : <option value="">{emptyLabel}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
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
 * A plain date input rather than a datetime picker: a deadline has no time of
 * day, and offering a time component invites people to believe in a precision the
 * data model does not have.
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
      <input
        type="date"
        value={draft}
        disabled={disabled || pending}
        onChange={(event) => void commit(event.target.value)}
      />
      {error ? (
        <span className="field__error" role="alert">
          {error}
        </span>
      ) : null}
    </label>
  )
}
