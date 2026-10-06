import { useI18n } from '../../../core/i18n'
import type { TranslationKey } from '../types'

/**
 * Table columns the person can show, hide and reorder.
 *
 * The layout is stored as an ordered list of visible ids rather than as a set of
 * flags, because "which columns, in what order" is one preference and splitting
 * it into a set plus a separate order is how the two drift apart.
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

export const COLUMN_LABELS: Record<ColumnId, TranslationKey> = {
  title: 'columns.column.title',
  status: 'columns.column.status',
  priority: 'columns.column.priority',
  assignee: 'columns.column.assignee',
  due_date: 'columns.column.due_date',
  project: 'columns.column.project',
  updated_at: 'columns.column.updated_at',
  created_at: 'columns.column.created_at',
}

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

const STORAGE_KEY = 'tasktracker.taskColumns'

function isColumnId(value: unknown): value is ColumnId {
  return typeof value === 'string' && (COLUMN_IDS as readonly string[]).includes(value)
}

/**
 * The saved layout, repaired rather than trusted.
 *
 * A stored layout written by an older build - or a hand-edited one - can be
 * missing columns that now exist, list a column that no longer does, or repeat
 * one. All three would render as a broken table, so the value is normalised here
 * instead of being defended against at every read.
 */
export function readColumns(): ColumnId[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_COLUMNS
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return DEFAULT_COLUMNS

    const seen = new Set<ColumnId>()
    const ordered: ColumnId[] = []
    for (const entry of parsed) {
      if (!isColumnId(entry) || seen.has(entry)) continue
      seen.add(entry)
      ordered.push(entry)
    }
    // The required columns are added back if the stored layout dropped them.
    for (const required of REQUIRED_COLUMNS) {
      if (!seen.has(required)) ordered.unshift(required)
    }
    return ordered
  } catch {
    return DEFAULT_COLUMNS
  }
}

export function writeColumns(columns: ColumnId[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(columns))
  } catch {
    /* preference only */
  }
}

/** Hidden columns are the ones the saved layout leaves out. */
export function hiddenColumns(columns: ColumnId[]): ColumnId[] {
  return COLUMN_IDS.filter((id) => !columns.includes(id))
}

/** Move one column by `offset` places, keeping the rest in order. */
export function moveColumn(columns: ColumnId[], from: number, offset: number): ColumnId[] {
  const next = [...columns]
  const target = from + offset
  if (target < 0 || target >= next.length) return columns
  const [moved] = next.splice(from, 1)
  if (moved === undefined) return columns
  next.splice(target, 0, moved)
  return next
}

/** Drop `dragged` at the position `over` currently occupies. */
export function reorder(columns: ColumnId[], dragged: ColumnId, over: ColumnId): ColumnId[] {
  const from = columns.indexOf(dragged)
  const target = columns.indexOf(over)
  if (from === -1 || target === -1 || from === target) return columns
  return moveColumn(columns, from, target - from)
}

/** A hook so a component gets the layout and the setter without re-plumbing it. */
export function useColumns(): {
  columns: ColumnId[]
  setColumns: (next: ColumnId[]) => void
  reset: () => void
  label: (id: ColumnId) => string
} {
  const { t } = useI18n()
  const columns = readColumns()
  return {
    columns,
    setColumns: (next: ColumnId[]) => writeColumns(next),
    reset: () => writeColumns(DEFAULT_COLUMNS),
    label: (id: ColumnId) => t(COLUMN_LABELS[id]),
  }
}
