import { useEffect, useState } from 'react'

import { useI18n } from '../../../core/i18n'
import { NavRow } from '../../../core/layout/NavRow'
import type { NavigatorGroup } from '../../../core/layout/navigator'
import type { TaskFilters } from '../types'
import { filtersFromSearch, filtersToSearch } from './TaskFilterBar'
import { readSavedFilters, SAVED_FILTERS_EVENT } from './savedFilters'
import type { SavedFilter } from './savedFilters'

/**
 * The rows of the "Сохранённые фильтры" submenu (stage 1.9).
 *
 * Saved filters are per-browser, so the list is read from storage rather than
 * fetched, and it re-reads itself on the change event: saving a filter in the
 * filter bar must show up here without waiting for a navigation.
 */
export function SavedFiltersRows({ onNavigate }: { onNavigate: () => void }) {
  const { t } = useI18n()
  const [saved, setSaved] = useState<SavedFilter[]>(readSavedFilters)

  useEffect(() => {
    const refresh = () => setSaved(readSavedFilters())
    window.addEventListener(SAVED_FILTERS_EVENT, refresh)
    // Another tab may have edited the same list.
    window.addEventListener('storage', refresh)
    return () => {
      window.removeEventListener(SAVED_FILTERS_EVENT, refresh)
      window.removeEventListener('storage', refresh)
    }
  }, [])

  if (saved.length === 0) {
    return (
      <li>
        <p className="nav__empty">{t('savedFilters.empty')}</p>
      </li>
    )
  }

  return (
    <>
      {saved.map((entry) => {
        const target = filtersToSearch(entry.filters as TaskFilters)
        return (
          <li key={entry.name}>
            <NavRow
              to={`/tasks${target}`}
              matches={target}
              icon="filter"
              label={entry.name}
              onNavigate={onNavigate}
            />
          </li>
        )
      })}
    </>
  )
}

/**
 * The submenu itself, declared in the module that owns it and registered by
 * the app layer (stage 1.9). The shell never sees this file; the registry in
 * `core/layout/navigator.ts` is the whole contract.
 */
export const savedFiltersNavigatorGroup: NavigatorGroup = {
  section: 'tasks',
  id: 'tasks.saved-filters',
  titleKey: 'savedFilters.title',
  icon: 'filter',
  // The group unfolds itself when the URL already carries one of the saved
  // filters, so applying one from elsewhere leaves the navigator showing
  // which view is open.
  active: ({ search }) => {
    const current = filtersToSearch(filtersFromSearch(search))
    return readSavedFilters().some(
      (entry) => filtersToSearch(entry.filters as TaskFilters) === current,
    )
  },
  content: ({ onNavigate }) => <SavedFiltersRows onNavigate={onNavigate} />,
}
