/**
 * Date and text formatting.
 *
 * All of it is locale-aware through `Intl`, and every helper tolerates the empty
 * case: a task without a deadline must render as a dash, not as "Invalid Date",
 * which is what `new Date(null).toLocaleDateString()` produces.
 *
 * The helpers take `t` rather than importing it, because a component that is not
 * inside the provider - a unit test, a storybook - can then pass its own stub
 * instead of failing on a missing context.
 */
import type { Translate } from './i18n'

const DATE_FORMAT: Intl.DateTimeFormatOptions = { year: 'numeric', month: 'short', day: 'numeric' }
const DATE_TIME_FORMAT: Intl.DateTimeFormatOptions = { dateStyle: 'medium', timeStyle: 'short' }

export const EMPTY = '—'

/** A `YYYY-MM-DD` string, rendered as a date and never shifted by a timezone. */
export function formatDate(value: string | null | undefined, locale?: string): string {
  if (!value) return EMPTY
  const parsed = new Date(`${value}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return EMPTY
  return parsed.toLocaleDateString(locale, DATE_FORMAT)
}

export function formatDateTime(value: string | null | undefined, locale?: string): string {
  if (!value) return EMPTY
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return EMPTY
  return parsed.toLocaleString(locale, DATE_TIME_FORMAT)
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
 * A deadline in words, because "3 days overdue" is the thing a person needs and a
 * bare date makes them do the arithmetic themselves.
 */
export function describeDueDate(
  value: string | null | undefined,
  t: Translate,
): string | null {
  const days = daysUntil(value)
  if (days === null) return null
  if (days === 0) return t('due.today')
  if (days === 1) return t('due.tomorrow')
  if (days === -1) return t('due.yesterday')
  if (days < 0) return t('due.overdue', { count: Math.abs(days) })
  if (days <= 7) return t('due.inDays', { count: days })
  return null
}

/** "3 comments" / "1 comment", so the plural rule is not hardcoded twice. */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`
}
