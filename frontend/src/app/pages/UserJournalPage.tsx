import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { activityApi } from '../../core/activity/api'
import { useAsync } from '../../core/hooks/useAsync'
import { useI18n } from '../../core/i18n'
import type { TranslationKey } from '../../core/i18n'
import { Icon } from '../../core/layout/Icon'
import { useOrganization } from '../../core/organizations/OrganizationContext'
import { RequiresOrganization } from '../../core/organizations/RequiresOrganization'
import { useCapabilities } from '../../core/permissions/capabilities'
import { Listbox } from '../../core/ui/Listbox'
import { Pagination } from '../../core/ui/Pagination'
import { ActivityFeed } from '../../core/activity/ActivityFeed'

/**
 * What one person has done here (stage 2.11).
 *
 * The feed already answered this with `actor_id` in the query; what was missing
 * was somebody asking the question that way. A journal is worth having as its
 * own screen for three reasons, and each one is a reason the link with parameters
 * would not do:
 *
 * * the person is **named in the URL** rather than chosen from a list, so the
 *   screen cannot be pointed at the wrong colleague by a misclick - and it can
 *   be linked to, which is what "look at what they did" usually is;
 * * the filters are the ones that make sense about a person (what, and when)
 *     rather than the feed's full set, which includes "who";
 * * and it is read **forwards** - what did they do last - so it pages newest
 *   first like the feed, and a page turn cannot hide an event that arrived while
 *   somebody was reading.
 *
 * The permission is `activity.view`, the same one the feed itself needs, and that
 * is deliberate: this is a filtered view of a feed the reader can already open.
 * Requiring an administrator's right here would gate a *narrower* view behind a
 * *higher* bar than the wide one, which is a way of saying "we trust you to read
 * everything but not to read one person".
 */
export function UserJournalPage() {
  return (
    <RequiresOrganization>
      <Journal />
    </RequiresOrganization>
  )
}

const PAGE_SIZE = 25

/** The windows a person actually asks about, rather than a date picker. */
const PERIODS = ['all', 'day', 'week', 'month'] as const
type Period = (typeof PERIODS)[number]

const ACTIONS = [
  'all',
  'task.created',
  'task.updated',
  'task.completed',
  'task.assigned',
  'comment.created',
  'user.profile_updated',
  'file.created',
] as const

function sinceFor(period: Period): string | undefined {
  if (period === 'all') return undefined
  const days = period === 'day' ? 1 : period === 'week' ? 7 : 30
  return new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString()
}

function Journal() {
  const { t } = useI18n()
  const { userId } = useParams<{ userId: string }>()
  const { current: organization } = useOrganization()
  const organizationId = organization?.id ?? null

  const [period, setPeriod] = useState<Period>('all')
  const [action, setAction] = useState<string>('all')
  const [offset, setOffset] = useState(0)

  const capabilities = useCapabilities(organizationId)
  const page = useAsync(
    () =>
      userId && organizationId
        ? activityApi.forPerson(organizationId, {
            actorId: userId,
            action: action === 'all' ? undefined : action,
            since: sinceFor(period),
            limit: PAGE_SIZE,
            offset,
          })
        : Promise.resolve(null),
    [userId, organizationId, period, action, offset],
  )

  if (!capabilities.canViewActivity) {
    return <p className="notice">{t('journal.denied')}</p>
  }

  return (
    <section className="panel">
      <header className="page-header">
        <div>
          <Link to={`/users/${userId}`} className="link">
            <Icon name="chevron" size={14} className="back-chevron" />
            {t('journal.back')}
          </Link>
          <h2>{t('journal.title')}</h2>
        </div>
      </header>

      <div className="fields">
        <label className="field">
          <span>{t('journal.period')}</span>
          <Listbox<Period>
            value={period}
            options={PERIODS.map((value) => ({ value, label: t(`journal.period_${value}`) }))}
            onChange={(next) => {
              if (next === null) return
              setPeriod(next)
              setOffset(0)
            }}
          />
        </label>
        <label className="field">
          <span>{t('journal.action')}</span>
          <Listbox<string>
            value={action}
            options={ACTIONS.map((value) => ({
              value,
              label: value === 'all' ? t('journal.action_all') : t(`activity.action.${value}` as TranslationKey),
            }))}
            onChange={(next) => {
              if (next === null) return
              setAction(next)
              setOffset(0)
            }}
          />
        </label>
      </div>

      {page.loading && !page.data ? <p className="notice">{t('app.loading')}</p> : null}
      {page.error ? <p className="notice notice--error">{page.error}</p> : null}

      {page.data ? (
        page.data.items.length === 0 ? (
          <p className="muted">{t('journal.empty')}</p>
        ) : (
          <>
            <ActivityFeed items={page.data.items} />
            <Pagination
              total={page.data.total}
              limit={page.data.limit}
              offset={offset}
              label={t('journal.title')}
              onChange={setOffset}
            />
          </>
        )
      ) : null}
    </section>
  )
}