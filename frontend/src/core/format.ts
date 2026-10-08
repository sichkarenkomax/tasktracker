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
const DEADLINE_FORMAT: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
}

export const EMPTY = '—'

const BARE_DATE = /^\d{4}-\d{2}-\d{2}$/

/**
 * A value that may be either a bare `YYYY-MM-DD` or a full instant.
 *
 * A bare date is anchored at *local* midnight so that rendering it cannot move it
 * to the previous or next day depending on the reader's zone - the reason the old
 * deadline column could be formatted safely. Anything carrying a time is an
 * instant ("a deadline can be 18:00") and is rendered in the reader's own zone,
 * because that is the only place its meaning is unambiguous.
 */
function parseDateOrInstant(value: string): Date {
  return BARE_DATE.test(value) ? new Date(`${value}T00:00:00`) : new Date(value)
}

function hasTime(value: string): boolean {
  return !BARE_DATE.test(value) && !Number.isNaN(new Date(value).getTime())
}

/** A date, or a date and time when the value carries one, never shifted. */
export function formatDate(value: string | null | undefined, locale?: string): string {
  if (!value) return EMPTY
  const parsed = parseDateOrInstant(value)
  if (Number.isNaN(parsed.getTime())) return EMPTY
  return parsed.toLocaleDateString(locale, DATE_FORMAT)
}

/** The deadline as written: "8 окт. 2026, 18:00" for an instant, a plain date otherwise. */
export function formatDeadline(value: string | null | undefined, locale?: string): string {
  if (!value) return EMPTY
  const parsed = parseDateOrInstant(value)
  if (Number.isNaN(parsed.getTime())) return EMPTY
  return hasTime(value)
    ? parsed.toLocaleString(locale, DEADLINE_FORMAT)
    : parsed.toLocaleDateString(locale, DATE_FORMAT)
}

export function formatDateTime(value: string | null | undefined, locale?: string): string {
  if (!value) return EMPTY
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return EMPTY
  return parsed.toLocaleString(locale, DATE_TIME_FORMAT)
}

/** Whole days from today; negative means the day has passed. */
export function daysUntil(value: string | null | undefined): number | null {
  if (!value) return null
  const target = parseDateOrInstant(value)
  if (Number.isNaN(target.getTime())) return null
  const today = new Date()
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const startOfTarget = new Date(target.getFullYear(), target.getMonth(), target.getDate())
  return Math.round((startOfTarget.getTime() - startOfToday.getTime()) / 86_400_000)
}

/**
 * Whether the moment itself has passed.
 *
 * A day-only deadline is overdue once its day is over; a deadline that carries a
 * time is overdue once *that time* is past, so a task due at 18:00 is still open
 * for work at 17:00 even though the day has not changed. The list's red badge and
 * the server's `overdue` filter both mean this, so it is asked in one place.
 */
export function isOverdue(value: string | null | undefined): boolean {
  if (!value) return false
  if (!hasTime(value)) return (daysUntil(value) ?? 1) < 0
  const target = new Date(value)
  return !Number.isNaN(target.getTime()) && target.getTime() < Date.now()
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
