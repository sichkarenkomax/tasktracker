/**
 * Date and text formatting.
 *
 * All of it is locale-aware through `Intl`, and every helper tolerates the empty
 * case: a task without a deadline must render as a dash, not as "Invalid Date",
 * which is what `new Date(null).toLocaleDateString()` produces.
 */

const DATE_FORMAT: Intl.DateTimeFormatOptions = { year: 'numeric', month: 'short', day: 'numeric' }
const DATE_TIME_FORMAT: Intl.DateTimeFormatOptions = {
  dateStyle: 'medium',
  timeStyle: 'short',
}

export const EMPTY = '—'

/** A `YYYY-MM-DD` string, rendered as a date and never shifted by a timezone. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return EMPTY
  const parsed = new Date(`${value}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? EMPTY : parsed.toLocaleDateString(undefined, DATE_FORMAT)
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return EMPTY
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? EMPTY : parsed.toLocaleString(undefined, DATE_TIME_FORMAT)
}

/** Whole days from today; negative means the date has passed. */
export function daysUntil(value: string | null | undefined): number | null {
  if (!value) return null
  const target = new Date(`${value}T00:00:00`)
  if (Number.isNaN(target.getTime())) return null
  const today = new Date()
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.round((target.getTime() - startOfToday.getTime()) / 86_400_000)
}

/**
 * A deadline in words, because "3 days overdue" is the thing a person needs and
 * a bare date makes them do the arithmetic.
 */
export function describeDueDate(value: string | null | undefined): string | null {
  const days = daysUntil(value)
  if (days === null) return null
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  if (days === -1) return 'yesterday'
  if (days < 0) return `${Math.abs(days)} days overdue`
  if (days <= 7) return `in ${days} days`
  return null
}

/** "3 comments" / "1 comment", so the plural is not hardcoded twice. */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`
}
