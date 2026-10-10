import { useSyncExternalStore } from 'react'

/**
 * How much of a person the reader wants to see in the pickers (stage 2.5).
 *
 * Module state with listeners, exactly like the date format in `format.ts`, and
 * for the same reason: the value is a preference read from one place by every
 * picker, and the write happens on a screen far from where it is read. The shell
 * subscribes once so a change redraws the tree - without that the switch on the
 * preferences screen would save and leave the open pickers as they were.
 */

export const PEOPLE_INFO = ['full', 'names'] as const

export type PeopleInfo = (typeof PEOPLE_INFO)[number]

const DEFAULT_PEOPLE_INFO: PeopleInfo = 'full'

/** The value an untouched preference reads as - what the registry calls the default. */
export const PEOPLE_INFO_DEFAULT = DEFAULT_PEOPLE_INFO

let active: PeopleInfo = DEFAULT_PEOPLE_INFO
const listeners = new Set<() => void>()

export function setPeopleInfo(value: unknown): void {
  const next = typeof value === 'string' ? value : null
  active = (PEOPLE_INFO as ReadonlyArray<string>).includes(next ?? '')
    ? (next as PeopleInfo)
    : DEFAULT_PEOPLE_INFO
  for (const listener of listeners) listener()
}

export function getPeopleInfo(): PeopleInfo {
  return active
}

export function subscribePeopleInfo(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/**
 * Re-renders the caller when the preference changes.
 *
 * Only the shell needs it - the same arrangement as the date format in
 * `format.ts`. A picker calls `getPeopleInfo()` while rendering and the shell's
 * re-render brings it along.
 */
export function usePeopleInfo(): PeopleInfo {
  return useSyncExternalStore(subscribePeopleInfo, getPeopleInfo, getPeopleInfo)
}