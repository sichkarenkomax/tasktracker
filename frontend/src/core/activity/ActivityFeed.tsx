import { formatDateTime } from '../format'
import { useI18n } from '../i18n'
import type { ActivityItem } from './api'

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
 *
 * It lives in Core rather than in the tasks module because three of its four
 * callers do not concern tasks: a person's journal, a project, the project list.
 * While it sat in the module, those Core screens reached across into a module to
 * render a list of events that have nothing to do with tasks - the same
 * dependency, spelled backwards, that `api.ts` had.
 */
export interface ActivityFeedProps {
  items: ActivityItem[]
  actorNames?: ReadonlyMap<string, string>
}

function actorName(actorNames: ReadonlyMap<string, string> | undefined, id: string | null, fallback: string): string {
  if (id === null) return fallback
  return actorNames?.get(id) ?? fallback
}

export function ActivityFeed({ items, actorNames }: ActivityFeedProps) {
  const { t } = useI18n()

  if (items.length === 0) {
    return <p className="muted">{t('activity.empty')}</p>
  }

  return (
    <ol className="activity">
      {items.map((item) => (
        <li key={item.id} className="activity__item">
          <span className="activity__actor">
            {actorName(actorNames, item.actor_id, t('activity.system'))}
          </span>
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