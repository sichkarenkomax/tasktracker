import { useI18n } from '../../../core/i18n'
import { hiddenColumns, readColumns, writeColumns } from '../../../core/ui/columns'
import type { ColumnSet } from '../../../core/ui/columns'
import type { TranslationKey } from '../types'

/**
 * The task list's vocabulary of columns.
 *
 * The mechanism - the stored layout, its repair, the drag-and-drop panel - is
 * generic and lives in `core/ui/columns` and `core/ui/ColumnSettingsPanel`,
 * because the people list (2.17) offers the same thing. What is here is only
 * the part that is about tasks.
 */
export const COLUMN_IDS = [
  'title',
  'status',
  'priority',
  'assignee',
  'due_date',
  'project',
  'updated_at',
  'created_at',
] as const

export type ColumnId = (typeof COLUMN_IDS)[number]

/**
 * The title column cannot be hidden: a row of empty cells with checkboxes in it
 * is not a task list, and there is nothing else in the row to click.
 */
export const REQUIRED_COLUMNS: ReadonlySet<ColumnId> = new Set<ColumnId>(['title'])

/** Sensible starting point: what fits on a laptop without horizontal scrolling. */
export const DEFAULT_COLUMNS: ColumnId[] = [
  'title',
  'status',
  'priority',
  'assignee',
  'due_date',
  'updated_at',
]

/** Built lazily because the labels need the translator, which needs a context. */
export function columnSet(t: (key: TranslationKey) => string): ColumnSet<ColumnId> {
  const labels: Record<ColumnId, string> = {
    title: t('columns.column.title'),
    status: t('columns.column.status'),
    priority: t('columns.column.priority'),
    assignee: t('columns.column.assignee'),
    due_date: t('columns.column.due_date'),
    project: t('columns.column.project'),
    updated_at: t('columns.column.updated_at'),
    created_at: t('columns.column.created_at'),
  }
  return {
    ids: COLUMN_IDS,
    labels,
    required: REQUIRED_COLUMNS,
    defaults: DEFAULT_COLUMNS,
    storageKey: 'tasktracker.taskColumns',
  }
}

/** The saved layout, repaired rather than trusted (see `core/ui/columns`). */
export function taskColumns(t: (key: TranslationKey) => string): ColumnId[] {
  return readColumns(columnSet(t))
}

export function saveTaskColumns(
  t: (key: TranslationKey) => string,
  columns: ColumnId[],
): void {
  writeColumns(columnSet(t), columns)
}

export function hiddenTaskColumns(
  t: (key: TranslationKey) => string,
  columns: ColumnId[],
): ColumnId[] {
  return hiddenColumns(columnSet(t), columns)
}

/** A hook so a component gets the layout and the setter without re-plumbing it. */
export function useColumns(): {
  columns: ColumnId[]
  setColumns: (next: ColumnId[]) => void
  reset: () => void
  label: (id: ColumnId) => string
} {
  const { t } = useI18n()
  const set = columnSet(t)
  return {
    columns: readColumns(set),
    setColumns: (next: ColumnId[]) => writeColumns(set, next),
    reset: () => writeColumns(set, [...DEFAULT_COLUMNS]),
    label: (id: ColumnId) => set.labels[id],
  }
}