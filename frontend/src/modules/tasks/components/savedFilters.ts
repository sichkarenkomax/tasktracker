/**
 * Saved filters.
 *
 * A named set of the filters the task list understands, stored per browser. Not on
 * the server, and that is a deliberate choice rather than a missing feature: a
 * saved view is a personal preference ("what is overdue and mine"), two people on
 * the same backlog rarely want identical ones, and a table on the server would
 * need an owner, a name-uniqueness rule and an API before anybody could pin
 * anything. When sharing views arrives it belongs on the organization, and the
 * shape here - a name plus a filter object - is already what that would store.
 */
export interface SavedFilter {
  name: string
  /** Exactly the shape `TaskFilters` has, minus paging. */
  filters: Record<string, unknown>
}

const STORAGE_KEY = 'tasktracker.savedFilters'

/**
 * Fired after every successful write, so the navigator's saved-filters
 * submenu can refresh: it reads the same list, and localStorage itself is
 * silent within the tab that changed it.
 */
export const SAVED_FILTERS_EVENT = 'tasktracker:savedFiltersChanged'

/**
 * Read the saved list, repairing rather than trusting it.
 *
 * A value written by an older build can be a bare array, a list of strings from
 * before filters had names, or hand-edited nonsense. Dropping anything that does
 * not fit the shape is better than rendering a broken menu, and a person who loses
 * one stale entry has not lost anything they can still type.
 */
export function readSavedFilters(): SavedFilter[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []

    const saved: SavedFilter[] = []
    for (const entry of parsed) {
      if (
        entry &&
        typeof entry === 'object' &&
        typeof (entry as SavedFilter).name === 'string' &&
        (entry as SavedFilter).name.trim() !== '' &&
        (entry as SavedFilter).filters &&
        typeof (entry as SavedFilter).filters === 'object'
      ) {
        saved.push(entry as SavedFilter)
      }
    }
    return saved
  } catch {
    return []
  }
}

export function writeSavedFilters(saved: SavedFilter[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(saved))
    window.dispatchEvent(new Event(SAVED_FILTERS_EVENT))
  } catch {
    /* preference only */
  }
}

/** Replace a saved filter with the same name, or add it at the end. */
export function upsertSavedFilter(saved: SavedFilter[], entry: SavedFilter): SavedFilter[] {
  return [...saved.filter((item) => item.name !== entry.name), entry]
}

/** Remove by name; removing something absent is not an error. */
export function removeSavedFilter(saved: SavedFilter[], name: string): SavedFilter[] {
  return saved.filter((entry) => entry.name !== name)
}
