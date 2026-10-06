import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * A tiny request lifecycle, because every page needs the same four states and
 * getting the fifth one wrong is how stale data ends up on screen.
 *
 * The `nonce` returned by `reload` is the escape hatch for "the same request with
 * different inputs": callers pass the inputs as dependencies instead.
 */
export interface AsyncState<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

export function useAsync<T>(
  run: () => Promise<T>,
  dependencies: readonly unknown[],
): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [nonce, setNonce] = useState(0)

  // The latest callback, so a caller may pass an inline closure without making
  // it a dependency - that would refetch on every render.
  const runRef = useRef(run)
  runRef.current = run

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    runRef
      .current()
      .then((value) => {
        if (cancelled) return
        setData(value)
        setError(null)
      })
      .catch((cause: unknown) => {
        if (cancelled) return
        setError(cause instanceof Error ? cause.message : 'Request failed')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      // Without this, a filter change three requests ago can land after the
      // latest one and overwrite it with older rows.
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...dependencies, nonce])

  const reload = useCallback(() => setNonce((value) => value + 1), [])
  return { data, error, loading, reload }
}

/**
 * One-shot mutation helper: tracks "in flight" and the error to display, so a
 * form does not have to reimplement both.
 *
 * Two ways to call it, and the difference matters. `run` swallows the failure and
 * resolves to `null`, which is right for a page that renders `error` itself.
 * `runOrThrow` re-raises, which is right for a child component that has to undo
 * its own optimistic edit - without it, a rejected save would leave a control
 * showing a value the server never accepted.
 */
export interface Mutation<TInput, TResult> {
  run: (input: TInput) => Promise<TResult | null>
  runOrThrow: (input: TInput) => Promise<TResult>
  pending: boolean
  error: string | null
  clearError: () => void
}

export function useMutation<TInput, TResult>(
  action: (input: TInput) => Promise<TResult>,
): Mutation<TInput, TResult> {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const actionRef = useRef(action)
  actionRef.current = action

  const runOrThrow = useCallback(async (input: TInput) => {
    setPending(true)
    setError(null)
    try {
      return await actionRef.current(input)
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'Request failed')
      throw cause
    } finally {
      setPending(false)
    }
  }, [])

  const run = useCallback(
    async (input: TInput) => {
      try {
        return await runOrThrow(input)
      } catch {
        return null
      }
    },
    [runOrThrow],
  )

  const clearError = useCallback(() => setError(null), [])
  return { run, runOrThrow, pending, error, clearError }
}
