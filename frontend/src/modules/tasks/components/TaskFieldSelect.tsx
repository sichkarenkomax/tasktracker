import { useEffect, useState } from 'react'

/**
 * A labelled select for one task field.
 *
 * Edits are committed on blur rather than on every keystroke: a select has no
 * intermediate state worth previewing, and firing a PATCH per change while
 * somebody is tabbing through the header would publish a `task.status_changed`
 * event per field they merely passed over.
 */
export interface TaskFieldSelectProps<T extends string> {
  label: string
  value: T | null
  options: ReadonlyArray<{ value: T; label: string }>
  emptyLabel: string
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
        <option value="">{emptyLabel}</option>
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
