import { api } from '../api/client'
import { buildQuery } from '../api/client'

/**
 * The activity feed (docs/architecture.md §19).
 *
 * This client lived in `modules/tasks` even though the endpoint is Core's -
 * Activity is a universal projection written by a wildcard subscriber, and a
 * client that says otherwise is a client the next module cannot use without
 * importing the task module first. Core pages (the project list, and since
 * 2.11 the journal on a person's profile) were already importing across that
 * line; it is drawn correctly here.
 */

export interface ActivityItem {
  id: string
  organization_id: string
  actor_id: string | null
  action: string
  entity_type: string | null
  entity_id: string | null
  summary: string | null
  created_at: string
}

export interface ActivityPage {
  items: ActivityItem[]
  total: number
  limit: number
  offset: number
}

export interface JournalQuery {
  actorId: string
  action?: string
  entityType?: string
  /** ISO moment; the journal shows what happened after it. */
  since?: string
  limit?: number
  offset?: number
}

export const activityApi = {
  forOrganization(organizationId: string, limit = 25): Promise<ActivityPage> {
    return api.get<ActivityPage>(
      `/activity${buildQuery({ organization_id: organizationId, limit })}`,
    )
  },

  /**
   * The feed of one entity.
   *
   * Used by the task page, where §31 puts Activity next to Comments. A comment
   * publishes `entity_type=task`, so asking per task returns comment activity too.
   */
  forEntity(
    organizationId: string,
    entityType: string,
    entityId: string,
    limit = 25,
  ): Promise<ActivityPage> {
    return api.get<ActivityPage>(
      `/activity/entity/${entityType}/${entityId}${buildQuery({
        organization_id: organizationId,
        limit,
      })}`,
    )
  },

  /**
   * One person's journal (stage 2.11).
   *
   * The same endpoint as the feed with the actor fixed: the filter already
   * existed, and what was missing was a screen that uses it. Nothing here sends
   * an organization the caller could have invented - it is always the one the
   * caller is looking at, and the server refuses the mismatch anyway.
   */
  forPerson(organizationId: string, query: JournalQuery): Promise<ActivityPage> {
    return api.get<ActivityPage>(
      `/activity${buildQuery({
        organization_id: organizationId,
        actor_id: query.actorId,
        action: query.action,
        entity_type: query.entityType,
        since: query.since,
        limit: query.limit,
        offset: query.offset,
      })}`,
    )
  },
}