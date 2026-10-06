import { formatDateTime } from '../../../core/format'
import type { ActivityItem } from '../types'

/**
 * The Activity feed.
 *
 * Every row is one line of readable text produced by the backend (`summary`).
 * The UI never assembles that sentence itself: the wording lives with the domain
 * logic that produced the event, so a task module added later reads correctly
 * here without any change to Core or to this component (section 19).
 *
 * The feed also answers *who*, which the acceptance criteria require: `actor_id`
 * arrives as a uuid, so the name is resolved against the organization roster the
 * caller already fetched rather than by asking the API per row.
 */
export interface ActivityFeedProps {
  items: ActivityItem[]
  actorNames?: ReadonlyMap<string, string>
}

function actorName(actorNames: ReadonlyMap<string, string> | undefined, id: string | null): string {
  if (id === null) return 'System'
  return actorNames?.get(id) ?? 'Someone'
}

export function ActivityFeed({ items, actorNames }: ActivityFeedProps) {
  if (items.length === 0) {
    return <p className="muted">Nothing has happened here yet.</p>
  }

  return (
    <ol className="activity">
      {items.map((item) => (
        <li key={item.id} className="activity__item">
          <span className="activity__actor">{actorName(actorNames, item.actor_id)}</span>
          <span className="activity__summary">{item.summary ?? item.action}</span>
          <time className="activity__time" dateTime={item.created_at}>
            {formatDateTime(item.created_at)}
          </time>
          <span className="activity__action">{item.action}</span>
        </li>
      ))}
    </ol>
  )
}
