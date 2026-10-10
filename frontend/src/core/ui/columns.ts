/**
 * Which columns a table shows, in what order.
 *
 * The mechanism, not the vocabulary: the task list (stage 3.x) and the merged
 * people list (stage 2.17) both want a layout the reader can rearrange and hide
 * columns in, and two copies of drag-and-drop, storage repair and a "these
 * columns cannot be hidden" rule is two things to fix twice. What each table
 * supplies is the small part that differs - the ids, their labels, and which of
 * them are load-bearing.
 *
 * The layout is stored as an *ordered list of visible ids* rather than a set of
 * flags, because "which columns, in what order" is one preference, and splitting
 * it into a set plus a separate order is how the two drift apart.
 */

/** Everything a table has to say about its columns. */
export interface ColumnSet<Id extends string> {
  /** Every column the table could show, including ones hidden by default. */
  ids: readonly Id[]
  labels: Record<Id, string>
  /** Columns that cannot be hidden - a table with no identity in it is a list
   *  of empty cells. */
  required?: ReadonlySet<Id>
  /** The starting layout: what fits on a laptop without horizontal scrolling. */
  defaults: Id[]
  /** localStorage key. One per table, or two tables would share a layout. */
  storageKey: string
}

export function hiddenColumns<Id extends string>(set: ColumnSet<Id>, columns: Id[]): Id[] {
  return set.ids.filter((id) => !columns.includes(id))
}

/** Move one column by `offset` places, keeping the rest in order. */
export function moveColumn<Id extends string>(columns: Id[], from: number, offset: number): Id[] {
  const next = [...columns]
  const target = from + offset
  if (target < 0 || target >= next.length) return columns
  const [moved] = next.splice(from, 1)
  if (moved === undefined) return columns
  next.splice(target, 0, moved)
  return next
}

/** Drop `dragged` at the position `over` currently occupies. */
export function reorder<Id extends string>(columns: Id[], dragged: Id, over: Id): Id[] {
  const from = columns.indexOf(dragged)
  const target = columns.indexOf(over)
  if (from === -1 || target === -1 || from === target) return columns
  return moveColumn(columns, from, target - from)
}

/**
 * The saved layout, repaired rather than trusted.
 *
 * A stored layout written by an older build - or a hand-edited one - can be
 * missing columns that now exist, list a column that no longer does, or repeat
 * one. All three would render as a broken table, so the value is normalised here
 * instead of being defended against at every read.
 */
export function readColumns<Id extends string>(set: ColumnSet<Id>): Id[] {
  const required = set.required ?? new Set<Id>()
  try {
    const raw = window.localStorage.getItem(set.storageKey)
    if (!raw) return [...set.defaults]
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return [...set.defaults]

    const seen = new Set<Id>()
    const ordered: Id[] = []
    for (const entry of parsed) {
      if (typeof entry !== 'string') continue
      if (!(set.ids as readonly string[]).includes(entry)) continue
      const id = entry as Id
      if (seen.has(id)) continue
      seen.add(id)
      ordered.push(id)
    }
    // The required columns are added back if the stored layout dropped them.
    for (const id of required) {
      if (!seen.has(id)) ordered.unshift(id)
    }
    return ordered
  } catch {
    return [...set.defaults]
  }
}

export function writeColumns<Id extends string>(set: ColumnSet<Id>, columns: Id[]): void {
  try {
    window.localStorage.setItem(set.storageKey, JSON.stringify(columns))
  } catch {
    /* preference only */
  }
}