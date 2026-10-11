import type { ReactNode } from 'react'

import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n'
import { describeLastSeen, isOnline } from './presence'

/**
 * The label next to a person's name (stage 2.10, contract only).
 *
 * Today it answers one question - is this person here - and reads presence. That
 * is deliberate: presence is the *last* thing a status should overwrite, because
 * it is the one that comes from behaviour rather than from somebody's claim. A
 * status a person sets ("in a meeting", "do not disturb") is something they
 * decided, and a dot saying they are here is something that happened; showing
 * both at once asks the reader to prefer one.
 *
 * So the shape is: a row of sources, each asked in turn, the first with an
 * answer wins. Presence is registered last and answers when nobody has spoken.
 * A status module registers itself ahead of it and is finished - it declares
 * which statuses exist, who may set which, and what one looks like, and it never
 * touches this file, the profile or the people list.
 *
 * **What a module provides:**
 *
 * * `read(subject)` - the status of that person, or `null` for "I have nothing";
 * * `render(status, subject)` - how it looks, including its own words;
 * * optionally `maySet(subject)` - whether this reader may change it, so a viewer
 *   looking at a colleague is never shown a control that would be refused.
 *
 * **What a module must not provide:** the dot, the words for being away, or a way
 * to say "definitely offline". Those are presence's, and a status module that can
 * answer them will eventually answer them differently.
 *
 * There is no table here and no storage: a status has no rows until a module that
 * uses it brings its own, and a table nobody reads is a table nobody migrates.
 */

/** Everything a source is allowed to know about the person being labelled. */
export interface StatusSubject {
  userId: string
  /** Whether this reader may see their presence at all (stage 2.9). */
  presenceVisible: boolean
  lastSeen: string | null | undefined
  /** The reader, for a source that offers a control rather than a label. */
  viewerId: string
  role: string | null
}

export interface StatusAnswer {
  /** Stable key of the status itself, for the words and for tests. */
  key: string
  /** Whatever the module needs to draw it - an emoji, an icon name, a label. */
  value: unknown
}

export interface StatusSource {
  /** Lower wins. Presence sits last so a claim never hides what happened. */
  readonly priority: number
  read(subject: StatusSubject): StatusAnswer | null
  render(answer: StatusAnswer, ctx: StatusRenderContext): ReactNode
  maySet?(subject: StatusSubject): boolean
}

/** What a source needs to draw itself.
 *
 * The translator travels here rather than being fetched inside `render`: a source
 * is a plain function, and a plain function that called `useI18n` would be
 * calling a hook from wherever it happened to run. That works until a source is
 * rendered twice on one screen, and fails in a way nobody can read. */
export interface StatusRenderContext {
  subject: StatusSubject
  t: (key: TranslationKey, values?: Record<string, string | number>) => string
  locale: string
}

const sources: StatusSource[] = []

/**
 * Adds a source and returns the way to take it back out.
 *
 * The unsubscribe is part of the signature rather than a convenience: a module
 * that registers once at import time never needs it, and a screen that
 * registers for its own lifetime cannot leak a source into the next one.
 */
export function registerStatusSource(source: StatusSource): () => void {
  sources.push(source)
  sources.sort((left, right) => left.priority - right.priority)
  return () => {
    const at = sources.indexOf(source)
    if (at !== -1) sources.splice(at, 1)
  }
}

/** The answer, or null when nothing has one. Exported so a screen can ask the
 *  same question the label asks, without knowing the order. */
export function currentStatus(subject: StatusSubject): StatusAnswer | null {
  for (const source of sources) {
    const answer = source.read(subject)
    if (answer !== null) return answer
  }
  return null
}

/** Whether this reader may change the status at all. False while nobody may. */
export function maySetStatus(subject: StatusSubject): boolean {
  return sources.some((source) => source.maySet?.(subject) === true)
}

// The fallback is a source like any other, and the last one: presence answers
// when no module has. Registering it here rather than special-casing it in the
// label is what keeps "a status replaces the dot" from becoming "a status
// replaces the dot, except when it feels like it".
const PRESENCE_PRIORITY = 1000

registerStatusSource({
  priority: PRESENCE_PRIORITY,
  read: (subject) => {
    if (!subject.presenceVisible) return null
    if (isOnline(subject.lastSeen)) return { key: 'online', value: null }
    if (subject.lastSeen === null || subject.lastSeen === undefined) return null
    return { key: 'away', value: subject.lastSeen }
  },
  render: (answer, { t, locale }) => {
    if (answer.key === 'online') {
      return (
        <>
          <span className="presence__dot" aria-hidden="true" />
          {t('profile.presenceOnline')}
        </>
      )
    }
    return <>{describeLastSeen(answer.value as string, locale)}</>
  },
})

/**
 * What a person is doing, right now, above their name.
 *
 * With no status module installed this renders presence - exactly what the
 * profile and the people list showed before this file existed. That is the point
 * of the contract: the fallback is not a placeholder for the module, it is the
 * answer when nobody has anything better to say.
 */
export function UserStatusLabel({ subject, className }: { subject: StatusSubject; className?: string }) {
  const { t, locale } = useI18n()
  const ctx: StatusRenderContext = { subject, t, locale }

  if (!subject.presenceVisible) {
    return (
      <span className={className} title={t('profile.presenceHidden')}>
        {t('people.hidden')}
      </span>
    )
  }

  for (const source of sources) {
    const answer = source.read(subject)
    if (answer !== null) {
      return <span className={className}>{source.render(answer, ctx)}</span>
    }
  }
  return null
}