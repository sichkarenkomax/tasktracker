import type { ReactNode } from 'react'

import type { TranslationKey } from '../i18n'
import type { IconName } from './Icon'

/**
 * The rail's four sections (stage 1.9).
 *
 * Routes live outside this union - `/members`, `/users` and `/structure` are
 * all separate pages - but the rail no longer shows them separately, so the
 * navigator asks "which section am I in", not "which route".
 */
export type NavigatorSectionId = 'projects' | 'tasks' | 'people' | 'settings'

export interface NavigatorGroupContext {
  /** Close the mobile drawer once a row inside has been clicked. */
  onNavigate: () => void
}

export interface NavigatorLocation {
  pathname: string
  search: string
}

export interface NavigatorGroup {
  /** The rail section this submenu opens under. */
  section: NavigatorSectionId
  /** Unique across registrations; re-registering the id replaces it. */
  id: string
  /**
   * The submenu title, as a key rather than a string: registration happens at
   * module load, outside React, where `t` is not available.
   */
  titleKey: TranslationKey
  icon: IconName
  /** Whether the group should start open - usually "is the current URL inside". */
  active?: (location: NavigatorLocation) => boolean
  /**
   * The submenu's rows, as a fragment of `<li>` elements. Called on every
   * render of the section, but only mounted while the group is open.
   */
  content: (context: NavigatorGroupContext) => ReactNode
}

const groups: NavigatorGroup[] = []

/**
 * The seam between the shell and the modules (stage 1.9).
 *
 * The shell lives in `core`, and `core` never imports from `modules`, so it
 * cannot know what a section's submenu contains. Modules declare their submenu
 * here and the app layer performs the registration: dependencies keep pointing
 * inward, and the navigator gains a submenu without `core` growing a
 * dependency it must not have.
 */
export function registerNavigatorGroup(group: NavigatorGroup): void {
  const existing = groups.findIndex((item) => item.id === group.id)
  if (existing === -1) groups.push(group)
  else groups[existing] = group
}

export function navigatorGroupsFor(section: NavigatorSectionId): NavigatorGroup[] {
  return groups.filter((group) => group.section === section)
}
