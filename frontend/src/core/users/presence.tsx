import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n'

/**
 * "When was this person last here" (stage 2.9).
 *
 * One module for both screens that answer it - the person's card and the roster
 * - because the two must not disagree: a list that says "5 minutes ago" above a
 * card that says "yesterday" is not a rounding difference, it is a product that
 * cannot be trusted to say when anybody is at their desk.
 *
 * The rules the server set, kept here rather than asked for on every row:
 *
 * * seen within five minutes is **here now** - a dot and a word, not a timestamp,
 *   because "в сети, 21:04" reads as a stale number the moment it is read;
 * * anything older is a distance in words, rounded away from the person ("about
 *   an hour"), because a colleague asks "were they around this morning", not
 *   "what second did they load a page at";
 * * a person whose answer hides it says nothing at all. Not "—", not a dash with
 *   a tooltip: they were not asked whether to tell a stranger they were online,
 *   they were asked whether to tell the team, and the team is this screen.
 *
 * `Intl.RelativeTimeFormat` does the wording in the interface's language, so
 * there is no table of ours to translate and keep in step.
 */

/** How long a "last seen" still means "here now". The server uses the same
 *  window; the two disagreeing would show a dot for somebody the server has
 *  already decided is offline. */
export const ONLINE_WINDOW_MS = 5 * 60 * 1000

/** The order words get coarser, in words. Below a minute it is "just now";
 *  above a day the date is more useful than a count of days. */
const MINUTE = 60 * 1000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

export function isOnline(lastSeen: string | null | undefined, now = Date.now()): boolean {
  if (!lastSeen) return false
  const then = Date.parse(lastSeen)
  if (Number.isNaN(then)) return false
  return now - then <= ONLINE_WINDOW_MS
}

/** The words for a moment, in the interface's language.
 *
 * "now" for somebody seen seconds ago, "about an hour" for an hour, and a date
 * past a week - past that point the exact moment is noise, and a person reading
 * "19 days ago" learns nothing they would not learn from "in April".
 */
export function describeLastSeen(
  lastSeen: string | null | undefined,
  locale: string,
  now = Date.now(),
): string | null {
  if (!lastSeen) return null
  const then = Date.parse(lastSeen)
  if (Number.isNaN(then)) return null
  const elapsed = now - then
  const format = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  if (elapsed < MINUTE) return format.format(0, 'minute')
  if (elapsed < HOUR) return format.format(-Math.round(elapsed / MINUTE), 'minute')
  if (elapsed < DAY) return format.format(-Math.round(elapsed / HOUR), 'hour')
  if (elapsed < 7 * DAY) return format.format(-Math.round(elapsed / DAY), 'day')
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(then))
}

/** The dot alone, for the places that only say "here or not" (2.9).
 *
 * Renders nothing at all when the person is offline *or* when their answer hides
 * presence from this reader - the two are the same silence on purpose: a grey
 * dot next to somebody who chose privacy would say "they are not here" about
 * somebody whose answer was not asked.
 */
export function PresenceDot({
  lastSeen,
  visible,
}: {
  lastSeen: string | null | undefined
  visible: boolean
}) {
  const { t } = useI18n()
  if (!visible || !isOnline(lastSeen)) return null
  return (
    <span
      className="presence-dot"
      role="img"
      aria-label={t('profile.presenceOnline')}
      title={t('profile.presenceOnline')}
    />
  )
}

/** What the server says about this person's answer, in the words to show for it.
 *
 * Three different states, and the difference between the last two is the whole
 * point of stage 2.9: "never seen" is an absence of information, while "hidden"
 * is information that this reader is not entitled to. A shared dash would make
 * a person who chose privacy look like a person who has never logged in.
 */
export function PresenceLabel({
  lastSeen,
  visible,
  className,
}: {
  lastSeen: string | null | undefined
  visible: boolean
  className?: string
}) {
  const { t, locale } = useI18n()

  if (!visible) {
    return (
      <span className={className} title={t('profile.presenceHidden')}>
        {t('people.hidden')}
      </span>
    )
  }
  if (isOnline(lastSeen)) {
    return (
      <span className={`${className ?? ''} presence presence--online`.trim()}>
        <span className="presence__dot" aria-hidden="true" />
        {t('profile.presenceOnline')}
      </span>
    )
  }
  const words = describeLastSeen(lastSeen, locale)
  if (words === null) {
    return <span className={`${className ?? ''} muted`.trim()}>{t('people.never')}</span>
  }
  return (
    <span className={className} title={t('profile.presenceLastSeenTitle') as TranslationKey}>
      {words}
    </span>
  )
}