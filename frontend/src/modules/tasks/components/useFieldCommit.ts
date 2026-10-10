import { useEffect, useState } from 'react'

/**
 * The commit-on-change logic of the task's inline field editors.
 *
 * One hook rather than a copy per field: "write the new value at once, and put
 * the old one back if the server refused it" has to behave identically for the
 * status, the deadline and the responsible person, and three copies of a rule
 * about not lying about the state of the data is one copy too many.
 */
export function useFieldCommit<T extends string>(
  value: T | null,
  onCommit: (next: T | null) => Promise<void>,
) {
  const [draft, setDraft] = useState(value ?? '')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  // Re-sync when the server value changes underneath us - for example after a
  // reload picked up somebody else's edit. Without this the control would keep
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

  return { draft, error, pending, commit }
}