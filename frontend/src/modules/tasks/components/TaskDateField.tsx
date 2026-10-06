import { useEffect, useState } from 'react'

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
