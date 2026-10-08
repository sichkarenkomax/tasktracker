import { createContext, useContext } from 'react'

import type { NavigatorSectionId } from './navigator'

/**
 * Counts the rail shows next to a section's icon (overdue tasks, for now).
 *
 * A context rather than a prop, because of the direction of the dependencies:
 * `core` holds the rail and must not import from `modules`, while the number
 * belongs to the tasks module. The app layer sits between them and fills this in
 * - the same seam `registerNavigatorGroup` uses, one step smaller.
 */
export type RailBadges = Partial<Record<NavigatorSectionId, number>>

const RailBadgesContext = createContext<RailBadges>({})

export const RailBadgesProvider = RailBadgesContext.Provider

export function useRailBadges(): RailBadges {
  return useContext(RailBadgesContext)
}