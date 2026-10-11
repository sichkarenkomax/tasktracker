import { useI18n } from '../i18n'

/**
 * "Showing 1-25 of 178" with the two buttons around it (stage 2.11).
 *
 * This existed twice - once in the task table, once in the people list - and
 * the two had drifted: the task table wrote "of 178 tasks" and the people list
 * wrote a bare "of 178". Neither was wrong exactly, but the audience can tell
 * which screen they are on from a word appearing, and that is not a thing worth
 * being able to tell. The audience noun is now a prop, and the list that has one
 * says it while the journal that has none does not invent it.
 *
 * It renders nothing when everything fits on one page: a row of controls that
 * only ever says "1-25 of 20" is furniture, not information.
 */
export function Pagination({
  total,
  limit,
  offset,
  onChange,
  label,
  noun,
}: {
  total: number
  limit: number
  offset: number
  onChange: (offset: number) => void
  /** What the page is paging over, for the navigation's own name. */
  label: string
  /** "178 tasks" - the object being counted. Omit where there is no natural one. */
  noun?: string
}) {
  const { t } = useI18n()
  if (total <= limit) return null

  const from = offset + 1
  const to = Math.min(offset + limit, total)

  return (
    <nav className="pagination" aria-label={label}>
      <button
        type="button"
        className="button button--ghost"
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - limit))}
      >
        {t('pagination.previous')}
      </button>
      <span className="muted">
        {t('pagination.showing', { from, to, total: noun ? `${total} ${noun}` : total })}
      </span>
      <button
        type="button"
        className="button button--ghost"
        disabled={to >= total}
        onClick={() => onChange(offset + limit)}
      >
        {t('pagination.next')}
      </button>
    </nav>
  )
}