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

const DATE_TIME_FORMAT: Intl.DateTimeFormatOptions = { dateStyle: 'medium', timeStyle: 'short' }

export const EMPTY = '—'

const BARE_DATE = /^\d{4}-\d{2}-\d{2}$/

/**
 * Date formats, as ids the settings screens offer.
 *
 * `locale` is "whatever the reader's language says" and is the only one that is
 * not a fixed arrangement - which is why the four fixed ones are spelled out here
 * rather than derived from the locale. A format is stored by id, so a label can
 * be translated later without invalidating anybody's choice.
 */
export const DATE_FORMATS = ['YYYY-MM-DD', 'DD.MM.YYYY', 'MM/DD/YYYY', 'DD.MM.YY', 'locale'] as const

export type DateFormat = (typeof DATE_FORMATS)[number]

const DEFAULT_FORMAT: DateFormat = 'YYYY-MM-DD'

let activeFormat: DateFormat = DEFAULT_FORMAT

/**
 * The format dates are rendered in, set once the settings are known.
 *
 * Module state rather than a React context because every existing call site calls
 * `formatDate(value)` directly, and threading a format through forty of them is
 * a change with no upside: the value is a preference, read the same way the
 * language and the theme are read from one place.
 */
export function setDateFormat(format: string | null | undefined): void {
  activeFormat = (DATE_FORMATS as ReadonlyArray<string>).includes(format ?? '')
    ? (format as DateFormat)
    : DEFAULT_FORMAT
}

export function getDateFormat(): DateFormat {
  return activeFormat
}

/** The date as the reader asked for it, from its local calendar parts. */
function formatByPattern(parts: { y: number; m: number; d: number }): string {
  const dd = String(parts.d).padStart(2, '0')
  const mm = String(parts.m + 1).padStart(2, '0')
  // The last two digits, not a padded four: `padStart` pads but never truncates,
  // so "2026".padStart(2, "0") is still "2026" and DD.MM.YY would silently print
  // the full year.
  const yy = String(parts.y % 100).padStart(2, '0')
  switch (activeFormat) {
    case 'DD.MM.YYYY':
      return `${dd}.${mm}.${parts.y}`
    case 'MM/DD/YYYY':
      return `${mm}/${dd}/${parts.y}`
    case 'DD.MM.YY':
      return `${dd}.${mm}.${yy}`
    case 'locale':
      return `${parts.d} ${new Intl.DateTimeFormat(undefined, { month: 'long' }).format(
        new Date(parts.y, parts.m, 1),
      )} ${parts.y}`
    default:
      return `${parts.y}-${mm}-${dd}`
  }
}

function clockOf(value: string, locale?: string): string {
  return new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' }).format(
    new Date(value),
  )
}

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
export function formatDate(value: string | null | undefined, _locale?: string): string {
  if (!value) return EMPTY
  const parsed = parseDateOrInstant(value)
  if (Number.isNaN(parsed.getTime())) return EMPTY
  return formatByPattern({ y: parsed.getFullYear(), m: parsed.getMonth(), d: parsed.getDate() })
}

/** The deadline as written: the date in the reader's format, plus its time. */
export function formatDeadline(value: string | null | undefined, locale?: string): string {
  if (!value) return EMPTY
  const parsed = parseDateOrInstant(value)
  if (Number.isNaN(parsed.getTime())) return EMPTY
  const day = formatByPattern({
    y: parsed.getFullYear(),
    m: parsed.getMonth(),
    d: parsed.getDate(),
  })
  return hasTime(value) ? `${day}, ${clockOf(value, locale)}` : day
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
