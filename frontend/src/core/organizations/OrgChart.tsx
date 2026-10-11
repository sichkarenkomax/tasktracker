import { useMemo, useState } from 'react'
import type { DragEvent } from 'react'

import { useI18n } from '../i18n'
import { Icon } from '../layout/Icon'
import { Avatar } from '../users/Avatar'
import type { Member, OrgPosition, OrgStructure } from './api'
import { buildChart, departmentSubtree, peopleInSubtree, wouldReportLoop } from './chartLayout'
import type { ChartGroup, ChartNode } from './chartLayout'

/**
 * The org chart: departments as boxes, people inside them.
 *
 * Two modes over one drawing. Read mode draws the structure; edit mode adds the
 * three gestures a mindmap editor is made of, all of them a drag with an
 * explicit drop target:
 *
 * * a department onto a department re-parents it,
 * * a person onto a department places them there,
 * * a person onto a person makes the target their manager;
 *
 * plus collapse, which is useful in either mode. The cycle guards run before
 * any request goes out - a gesture that would corrupt the chart does nothing
 * and says why, rather than round-tripping to the server for a refusal.
 */
export interface OrgChartProps {
  structure: OrgStructure
  members: Member[]
  onSelect: (userId: string) => void
  selectedUserId: string | null
  editable?: boolean
  selectedDepartmentId?: string | null
  onSelectDepartment?: (departmentId: string, anchor: HTMLElement) => void
  onReparentDepartment?: (departmentId: string, parentId: string | null) => Promise<void>
  onReorderDepartment?: (
    departmentId: string,
    targetId: string,
    zone: 'before' | 'after',
  ) => Promise<void>
  onPlacePerson?: (userId: string, departmentId: string | null) => Promise<void>
  onAssignManager?: (userId: string, managerId: string) => Promise<void>
  onAddDepartment?: (parentId: string, anchor: HTMLElement) => void
  onGestureError?: (message: string) => void
}

type DragPayload = { kind: 'department'; id: string } | { kind: 'person'; id: string }

/**
 * Where in a box a drop would land.
 *
 * `inside` is what a drop in the middle means and always has meant. The two
 * edges are new, and they are what makes a block movable *sideways* rather than
 * only nestable: a department dragged to the left edge of a sibling goes in
 * front of it, to the right edge - behind it, and only the middle changes its
 * parent.
 *
 * People have one zone. A person belongs in a department or nowhere; "before
 * Sales" is not a place a person can be.
 */
type DropZone = 'inside' | 'before' | 'after'

/** What the pointer is currently over, and in which of its three zones. */
interface DragOver {
  key: string
  zone: DropZone
}

/** The outer fifth on each side is a reorder zone; the middle nests. */
const EDGE_ZONE = 0.2

function dropZoneFor(
  payload: DragPayload | null,
  box: HTMLElement,
  clientX: number,
): DropZone {
  if (payload === null || payload.kind !== 'department') return 'inside'
  const rect = box.getBoundingClientRect()
  const edge = rect.width * EDGE_ZONE
  if (clientX < rect.left + edge) return 'before'
  if (clientX > rect.right - edge) return 'after'
  return 'inside'
}

/** The envelope every drag carries, in `text/plain` for maximal compatibility. */
function readPayload(dataTransfer: DataTransfer | null): DragPayload | null {
  if (!dataTransfer) return null
  try {
    const parsed: unknown = JSON.parse(dataTransfer.getData('text/plain'))
    if (typeof parsed !== 'object' || parsed === null) return null
    const { kind, id } = parsed as { kind?: unknown; id?: unknown }
    if ((kind === 'department' || kind === 'person') && typeof id === 'string') {
      return { kind, id }
    }
  } catch {
    /* not our payload - an image dragged in, or plain text */
  }
  return null
}

export function OrgChart({
  structure,
  members,
  onSelect,
  selectedUserId,
  editable = false,
  selectedDepartmentId = null,
  onSelectDepartment,
  onReparentDepartment,
  onReorderDepartment,
  onPlacePerson,
  onAssignManager,
  onAddDepartment,
  onGestureError,
}: OrgChartProps) {
  const { t } = useI18n()
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set())
  const [dragOver, setDragOver] = useState<DragOver | null>(null)

  const positionsById = useMemo(
    () => new Map(structure.positions.map((position) => [position.id, position])),
    [structure.positions],
  )

  const chart = useMemo(
    () => buildChart(structure.departments, members, structure.placements),
    [structure.departments, members, structure.placements],
  )

  const editor = {
    editable,
    selectedDepartmentId,
    structure,
    collapsed,
    dragOver,
    onSelectDepartment,
    onReparentDepartment,
    onReorderDepartment,
    onPlacePerson,
    onAssignManager,
    onAddDepartment,
    onGestureError,
    setCollapsed,
    setDragOver,
  }

  if (chart.roots.length === 0 && chart.unplaced.length === 0) {
    return <p className="notice">{t('org.chartEmpty')}</p>
  }

  return (
    <div
      className={[
        'orgchart-wrap',
        // Dropping on the empty space around the tree takes a department out to
        // the top level. The alternative was a "make it a root" button, and the
        // gesture people already expect from a tree - let it go - was refused.
        editable && dragOver?.key === 'root' ? 'orgchart-wrap--root' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      onDragOver={(event) => {
        if (!editable) return
        if (readPayload(event.dataTransfer)?.kind !== 'department') return
        // Children stop propagation, so this only sees the empty space between
        // and around the boxes.
        event.preventDefault()
        event.dataTransfer.dropEffect = 'move'
        if (dragOver?.key !== 'root') setDragOver({ key: 'root', zone: 'inside' })
      }}
      onDrop={(event) => {
        if (!editable) return
        const payload = readPayload(event.dataTransfer)
        if (payload?.kind !== 'department') return
        event.preventDefault()
        setDragOver(null)
        void onReparentDepartment?.(payload.id, null)
      }}
    >
      {editable ? <p className="orgnode__hint">{t('org.editHint')}</p> : null}

      <ul className="orgchart">
        {chart.roots.map((group) => (
          <DepartmentBox
            key={group.departmentId}
            group={group}
            positionsById={positionsById}
            members={members}
            selectedUserId={selectedUserId}
            onSelect={onSelect}
            editor={editor}
          />
        ))}
      </ul>

      {chart.unplaced.length > 0 ? (
        <UnplacedBox
          people={chart.unplaced}
          positionsById={positionsById}
          selectedUserId={selectedUserId}
          onSelect={onSelect}
          editor={editor}
        />
      ) : null}
    </div>
  )
}

/** The position title to draw on a card, or null when they hold none. */
function titleOf(person: ChartNode, positions: Map<string, OrgPosition>): string | null {
  if (!person.positionId) return null
  return positions.get(person.positionId)?.title ?? null
}

interface EditorState {
  editable: boolean
  selectedDepartmentId: string | null
  structure: OrgStructure
  collapsed: ReadonlySet<string>
  dragOver: DragOver | null
  onSelectDepartment?: (departmentId: string, anchor: HTMLElement) => void
  onReparentDepartment?: (departmentId: string, parentId: string | null) => Promise<void>
  onReorderDepartment?: (
    departmentId: string,
    targetId: string,
    zone: 'before' | 'after',
  ) => Promise<void>
  onPlacePerson?: (userId: string, departmentId: string | null) => Promise<void>
  onAssignManager?: (userId: string, managerId: string) => Promise<void>
  onAddDepartment?: (parentId: string, anchor: HTMLElement) => void
  onGestureError?: (message: string) => void
  setCollapsed: (next: (previous: ReadonlySet<string>) => ReadonlySet<string>) => void
  setDragOver: (next: DragOver | null) => void
}

function DepartmentBox({
  group,
  positionsById,
  members,
  selectedUserId,
  onSelect,
  editor,
}: {
  group: ChartGroup
  positionsById: Map<string, OrgPosition>
  members: Member[]
  selectedUserId: string | null
  onSelect: (userId: string) => void
  editor: EditorState
}) {
  const { t } = useI18n()
  const { editable, structure } = editor

  const nameOf = (userId: string): string => {
    const member = members.find((item) => item.user_id === userId)
    return member ? member.first_name || member.username : t('activity.someone')
  }

  const isCollapsed = editor.collapsed.has(group.departmentId)
  const overKey = `department:${group.departmentId}`
  const zoneClass =
    editor.dragOver !== null && editor.dragOver.key === overKey
      ? `orgnode__box--drop-${editor.dragOver.zone}`
      : ''

  const deputyIds = structure.department_deputies[group.departmentId] ?? []
  const [firstDeputy] = deputyIds
  // What a collapsed box has to say for itself. A department with nothing in it
  // at all - no head, no deputy, nobody anywhere below, no sub-departments - says
  // nothing, and an empty body under a header is the frame that made an emptied
  // unit look like a leftover.
  const hasSomethingToSay =
    group.headId !== null ||
    deputyIds.length > 0 ||
    peopleInSubtree(group) > 0 ||
    group.children.length > 0

  const toggle = () =>
    editor.setCollapsed((previous) => {
      const next = new Set(previous)
      if (next.has(group.departmentId)) next.delete(group.departmentId)
      else next.add(group.departmentId)
      return next
    })

  const handleDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault()
    event.stopPropagation()
    editor.setDragOver(null)
    if (!editable) return
    const payload = readPayload(event.dataTransfer)
    if (payload === null) return

    const zone = dropZoneFor(payload, event.currentTarget, event.clientX)

    if (payload.kind === 'department') {
      if (payload.id === group.departmentId) return
      if (departmentSubtree(structure.departments, payload.id).has(group.departmentId)) {
        // A box can be dragged into its own subtree from the side as well as
        // from the middle, and the loop it would make is the same one.
        editor.onGestureError?.(t('org.departmentCycle'))
        return
      }
      if (zone === 'inside') {
        void editor.onReparentDepartment?.(payload.id, group.departmentId)
        return
      }
      void editor.onReorderDepartment?.(payload.id, group.departmentId, zone)
      return
    }
    void editor.onPlacePerson?.(payload.id, group.departmentId)
  }

  return (
    // A list item because that is what lets the connectors work: the CSS draws
    // the elbow from this node up to its siblings' bus and down from there to
    // every child, which needs the parent and its children to be siblings in the
    // markup rather than boxes nested inside one another.
    <li className="orgnode">
      <div
        className={[
          'orgnode__box',
          editor.selectedDepartmentId === group.departmentId ? 'orgnode__box--selected' : '',
          zoneClass,
        ]
          .filter(Boolean)
          .join(' ')}
        aria-label={group.name}
        onDragOver={(event) => {
          if (!editable) return
          event.preventDefault()
          event.stopPropagation()
          event.dataTransfer.dropEffect = 'move'
          const payload = readPayload(event.dataTransfer)
          const zone = dropZoneFor(payload, event.currentTarget, event.clientX)
          // Only write when the zone actually changed: setting state on every
          // pointer move over a box re-renders the whole chart per pixel.
          if (editor.dragOver?.key === overKey && editor.dragOver.zone === zone) return
          editor.setDragOver({ key: overKey, zone })
        }}
        onDragLeave={(event) => {
          if (event.currentTarget.contains(event.relatedTarget as Node | null)) return
          if (editor.dragOver?.key === overKey) editor.setDragOver(null)
        }}
        onDrop={handleDrop}
      >
        <header className="orgnode__head">
          <button
            type="button"
            className="icon-button orgnode__toggle"
            aria-expanded={!isCollapsed}
            aria-label={isCollapsed ? t('org.expand') : t('org.collapse')}
            onClick={toggle}
          >
            <Icon
              name="chevron"
              size={13}
              className={isCollapsed ? undefined : 'orgnode__chevron--open'}
            />
          </button>

          {editable ? (
            <button
              type="button"
              className="orgnode__name orgnode__name--draggable"
              draggable
              onDragStart={(event) => {
                event.dataTransfer.effectAllowed = 'move'
                event.dataTransfer.setData(
                  'text/plain',
                  JSON.stringify({ kind: 'department', id: group.departmentId }),
                )
              }}
              // The name folds the department. Opening it to edit is the button
              // beside it, so the two gestures do not share one target.
              onClick={toggle}
              aria-expanded={!isCollapsed}
            >
              {group.name}
            </button>
          ) : (
            <button
              type="button"
              className="orgnode__name"
              onClick={toggle}
              aria-expanded={!isCollapsed}
            >
              {group.name}
            </button>
          )}

          {editable ? (
            <span className="orgnode__actions">
              <button
                type="button"
                className="icon-button"
                aria-label={`${t('org.addSubdepartment')}: ${group.name}`}
                onClick={(event) => editor.onAddDepartment?.(group.departmentId, event.currentTarget)}
              >
                <Icon name="plus" size={12} />
              </button>
              <button
                type="button"
                className="icon-button"
                aria-label={`${t('org.departmentSettings')}: ${group.name}`}
                onClick={(event) =>
                  editor.onSelectDepartment?.(group.departmentId, event.currentTarget)
                }
              >
                <Icon name="edit" size={12} />
              </button>
            </span>
          ) : null}
        </header>

        {/* Collapsed, the body answers for the department: who runs it, who
            covers, how many. Expanded, it lists its own people and leaves the
            children to their own boxes. An empty body is not rendered at all -
            an emptied unit reads as a plain header rather than as a card that was
            filled once and has since lost its contents. */}
        {isCollapsed ? (
          hasSomethingToSay ? (
            <div className="orgnode__body">
              <p className="orgnode__line">
                <span className="orgnode__role">{t('org.departmentHead')}</span>
                <span>{group.headId ? nameOf(group.headId) : t('org.noManager')}</span>
              </p>
              {firstDeputy ? (
                <p className="orgnode__line">
                  <span className="orgnode__role">{t('org.departmentDeputy')}</span>
                  <span>
                    {nameOf(firstDeputy)}
                    {deputyIds.length > 1 ? ` +${deputyIds.length - 1}` : ''}
                  </span>
                </p>
              ) : null}
              <p className="orgnode__meta">
                {t('org.peopleCount', { count: peopleInSubtree(group) })}
              </p>
            </div>
          ) : null
        ) : group.people.length === 0 ? (
          // "Empty" means nothing underneath either: a department whose people
          // all sit in its sub-departments is not empty, it is a level above
          // them, and saying so next to five boxes below it reads as a bug.
          group.children.length === 0 ? (
            <div className="orgnode__body">
              <p className="orgnode__empty">{t('org.departmentEmpty')}</p>
            </div>
          ) : null
        ) : (
          <div className="orgnode__body">
            <div className="orgnode__people">
              {group.people.map((person) => (
                <PersonCard
                  key={person.userId}
                  node={person}
                  title={titleOf(person, positionsById)}
                  deputyCount={(structure.placements[person.userId]?.deputies ?? []).length}
                  selected={selectedUserId === person.userId}
                  onSelect={onSelect}
                  editor={editor}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {group.children.length > 0 && !isCollapsed ? (
        <ul className="orgnode__children">
          {group.children.map((child) => (
            <DepartmentBox
              key={child.departmentId}
              group={child}
              positionsById={positionsById}
              members={members}
              selectedUserId={selectedUserId}
              onSelect={onSelect}
              editor={editor}
            />
          ))}
        </ul>
      ) : null}
    </li>
  )
}

function UnplacedBox({
  people,
  positionsById,
  selectedUserId,
  onSelect,
  editor,
}: {
  people: ChartNode[]
  positionsById: Map<string, OrgPosition>
  selectedUserId: string | null
  onSelect: (userId: string) => void
  editor: EditorState
}) {
  const { t } = useI18n()
  const { editable } = editor
  const overKey = 'unplaced'

  return (
    // The same box as a node, but outside the tree: people with no department
    // hang from nothing, and drawing a connector to nowhere would invent a level
    // that is not in the data.
    <section
      className={[
        'orgunplaced',
        'orgnode__box',
        editor.dragOver?.key === overKey ? 'orgnode__box--drop-inside' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      aria-label={t('org.unplaced')}
      onDragOver={(event) => {
        if (!editable) return
        event.preventDefault()
        event.stopPropagation()
        event.dataTransfer.dropEffect = 'move'
        if (editor.dragOver?.key !== overKey) {
          editor.setDragOver({ key: overKey, zone: 'inside' })
        }
      }}
      onDragLeave={(event) => {
        if (event.currentTarget.contains(event.relatedTarget as Node | null)) return
        if (editor.dragOver?.key === overKey) editor.setDragOver(null)
      }}
      onDrop={(event) => {
        event.preventDefault()
        event.stopPropagation()
        editor.setDragOver(null)
        if (!editable) return
        const payload = readPayload(event.dataTransfer)
        if (payload?.kind === 'person') {
          void editor.onPlacePerson?.(payload.id, null)
          return
        }
        // A department dropped here becomes a top-level one. This used to be
        // refused on the grounds that un-nesting is a decision for the parent
        // picker - but the gesture had no other way to say it, and the picker
        // is still there for anybody who prefers a form.
        if (payload?.kind === 'department') {
          void editor.onReparentDepartment?.(payload.id, null)
        }
      }}
    >
      <header className="orgnode__head">
        <Icon name="members" size={13} />
        <span className="orgnode__name orgnode__name--static">{t('org.unplaced')}</span>
        <span className="orgnode__meta">{t('org.peopleCount', { count: people.length })}</span>
      </header>
      <div className="orgnode__body">
        <p className="orgnode__empty">{t('org.unplacedHint')}</p>
        <div className="orgnode__people">
          {people.map((person) => (
            <PersonCard
              key={person.userId}
              node={person}
              title={titleOf(person, positionsById)}
              selected={selectedUserId === person.userId}
              onSelect={onSelect}
              editor={editor}
            />
          ))}
        </div>
      </div>
    </section>
  )
}

function PersonCard({
  node,
  title,
  deputyCount = 0,
  selected,
  onSelect,
  editor,
}: {
  node: ChartNode
  title: string | null
  deputyCount?: number
  selected: boolean
  onSelect: (userId: string) => void
  editor: EditorState
}) {
  const { t } = useI18n()
  const { editable } = editor

  return (
    <button
      type="button"
      className={[
        'orgperson',
        editable ? 'orgperson--draggable' : '',
        selected ? 'orgperson--selected' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      draggable={editable}
      onDragStart={(event) => {
        if (!editable) return
        event.dataTransfer.effectAllowed = 'move'
        event.dataTransfer.setData(
          'text/plain',
          JSON.stringify({ kind: 'person', id: node.userId }),
        )
      }}
      onDragOver={(event) => {
        // Only a person payload matters here; a department dropped on a card
        // falls through to the box, which is the gesture that nests it.
        if (!editable || readPayload(event.dataTransfer)?.kind !== 'person') return
        event.preventDefault()
        event.stopPropagation()
        event.dataTransfer.dropEffect = 'move'
      }}
      onDrop={(event) => {
        const payload = readPayload(event.dataTransfer)
        if (payload?.kind !== 'person') return
        event.preventDefault()
        event.stopPropagation()
        editor.setDragOver(null)
        if (payload.id === node.userId) return
        if (wouldReportLoop(editor.structure.placements, payload.id, node.userId)) {
          editor.onGestureError?.(t('org.managerCycle'))
          return
        }
        void editor.onAssignManager?.(payload.id, node.userId)
      }}
      onClick={() => onSelect(node.userId)}
      aria-pressed={selected}
      // The name truncates rather than widening the card (2.13), so the full one
      // has to remain reachable: a card saying "Konstantin P…" and nothing else
      // does not tell the reader who it is.
      title={node.name}
    >
      <Avatar src={node.avatarUrl} name={node.name} size="sm" />
      <span className="orgperson__text">
        <span className="orgperson__name">{node.name}</span>
        <span className="orgperson__title">{title ?? t('org.noPosition')}</span>
      </span>
      {deputyCount > 0 ? (
        <span className="orgperson__deputies" title={t('org.deputies')}>
          <Icon name="eye" size={12} />
          {deputyCount}
        </span>
      ) : null}
    </button>
  )
}
