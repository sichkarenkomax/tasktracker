import { useMemo, useState } from 'react'
import type { DragEvent } from 'react'

import { useI18n } from '../i18n'
import { Icon } from '../layout/Icon'
import { Avatar } from '../users/Avatar'
import type { Member, OrgPosition, OrgStructure } from './api'
import { buildChart, departmentSubtree, textWidth, wouldReportLoop } from './chartLayout'
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
  onSelectDepartment?: (departmentId: string) => void
  onReparentDepartment?: (departmentId: string, parentId: string | null) => Promise<void>
  onPlacePerson?: (userId: string, departmentId: string | null) => Promise<void>
  onAssignManager?: (userId: string, managerId: string) => Promise<void>
  onAddDepartment?: (parentId: string) => void
  onGestureError?: (message: string) => void
}

type DragPayload = { kind: 'department'; id: string } | { kind: 'person'; id: string }

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
  onPlacePerson,
  onAssignManager,
  onAddDepartment,
  onGestureError,
}: OrgChartProps) {
  const { t } = useI18n()
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set())
  const [dragOver, setDragOver] = useState<string | null>(null)

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
    <div className="orgchart">
      {editable ? <p className="orgbox__hint">{t('org.editHint')}</p> : null}

      {chart.roots.map((group) => (
        <DepartmentBox key={group.departmentId} group={group} depth={0} positionsById={positionsById} members={members} selectedUserId={selectedUserId} onSelect={onSelect} editor={editor} />
      ))}

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
  dragOver: string | null
  onSelectDepartment?: (departmentId: string) => void
  onReparentDepartment?: (departmentId: string, parentId: string | null) => Promise<void>
  onPlacePerson?: (userId: string, departmentId: string | null) => Promise<void>
  onAssignManager?: (userId: string, managerId: string) => Promise<void>
  onAddDepartment?: (parentId: string) => void
  onGestureError?: (message: string) => void
  setCollapsed: (next: (previous: ReadonlySet<string>) => ReadonlySet<string>) => void
  setDragOver: (key: string | null) => void
}

function DepartmentBox({
  group,
  depth,
  positionsById,
  members,
  selectedUserId,
  onSelect,
  editor,
}: {
  group: ChartGroup
  depth: number
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

  const handleDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault()
    event.stopPropagation()
    editor.setDragOver(null)
    if (!editable) return
    const payload = readPayload(event.dataTransfer)
    if (payload === null) return

    if (payload.kind === 'department') {
      if (payload.id === group.departmentId) return
      if (departmentSubtree(structure.departments, payload.id).has(group.departmentId)) {
        editor.onGestureError?.(t('org.departmentCycle'))
        return
      }
      void editor.onReparentDepartment?.(payload.id, group.departmentId)
      return
    }
    void editor.onPlacePerson?.(payload.id, group.departmentId)
  }

  return (
    <section
      className={[
        'orgbox',
        editor.selectedDepartmentId === group.departmentId ? 'orgbox--selected' : '',
        editor.dragOver === overKey ? 'orgbox--dragover' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      style={{ marginInlineStart: `${depth * 1.5}rem` }}
      aria-label={group.name}
      onDragOver={(event) => {
        if (!editable) return
        event.preventDefault()
        event.stopPropagation()
        event.dataTransfer.dropEffect = 'move'
        if (editor.dragOver !== overKey) editor.setDragOver(overKey)
      }}
      onDragLeave={(event) => {
        if (event.currentTarget.contains(event.relatedTarget as Node | null)) return
        if (editor.dragOver === overKey) editor.setDragOver(null)
      }}
      onDrop={handleDrop}
    >
      <header className="orgbox__head">
        <button
          type="button"
          className="icon-button orgbox__toggle"
          aria-expanded={!isCollapsed}
          aria-label={isCollapsed ? t('org.expand') : t('org.collapse')}
          onClick={() =>
            editor.setCollapsed((previous) => {
              const next = new Set(previous)
              if (next.has(group.departmentId)) next.delete(group.departmentId)
              else next.add(group.departmentId)
              return next
            })
          }
        >
          <Icon name="chevron" size={14} className={isCollapsed ? undefined : 'orgbox__chevron--open'} />
        </button>

        {editable ? (
          <button
            type="button"
            className="orgbox__title orgbox__title--button orgbox__title--draggable"
            draggable
            onDragStart={(event) => {
              event.dataTransfer.effectAllowed = 'move'
              event.dataTransfer.setData(
                'text/plain',
                JSON.stringify({ kind: 'department', id: group.departmentId }),
              )
            }}
            onClick={() => editor.onSelectDepartment?.(group.departmentId)}
          >
            {group.name}
          </button>
        ) : (
          <span className="orgbox__title">{group.name}</span>
        )}
        {group.headId ? <span className="orgbox__head-name">{nameOf(group.headId)}</span> : null}
        <span className="muted">{t('org.peopleCount', { count: group.people.length })}</span>

        {editable ? (
          <span className="orgbox__actions">
            <button
              type="button"
              className="icon-button"
              aria-label={`${t('org.addSubdepartment')}: ${group.name}`}
              onClick={() => editor.onAddDepartment?.(group.departmentId)}
            >
              <Icon name="plus" size={13} />
            </button>
            <button
              type="button"
              className="icon-button"
              aria-label={`${t('org.departmentSettings')}: ${group.name}`}
              onClick={() => editor.onSelectDepartment?.(group.departmentId)}
            >
              <Icon name="edit" size={13} />
            </button>
          </span>
        ) : null}
      </header>

      {isCollapsed ? null : (
        <>
          <div className="orgbox__people">
            {group.people.length === 0 && group.children.length === 0 ? (
              <p className="orgbox__empty">{t('org.departmentEmpty')}</p>
            ) : null}

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

          {group.children.length > 0 ? (
            <div className="orgbox__children">
              {group.children.map((child) => (
                <DepartmentBox
                  key={child.departmentId}
                  group={child}
                  depth={depth + 1}
                  positionsById={positionsById}
                  members={members}
                  selectedUserId={selectedUserId}
                  onSelect={onSelect}
                  editor={editor}
                />
              ))}
            </div>
          ) : null}
        </>
      )}
    </section>
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
    <section
      className={[
        'orgbox',
        'orgbox--unplaced',
        editor.dragOver === overKey ? 'orgbox--dragover' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      aria-label={t('org.unplaced')}
      onDragOver={(event) => {
        if (!editable) return
        event.preventDefault()
        event.stopPropagation()
        event.dataTransfer.dropEffect = 'move'
        if (editor.dragOver !== overKey) editor.setDragOver(overKey)
      }}
      onDragLeave={(event) => {
        if (event.currentTarget.contains(event.relatedTarget as Node | null)) return
        if (editor.dragOver === overKey) editor.setDragOver(null)
      }}
      onDrop={(event) => {
        event.preventDefault()
        event.stopPropagation()
        editor.setDragOver(null)
        if (!editable) return
        const payload = readPayload(event.dataTransfer)
        // Dropping a department here would silently un-nest it; the parent
        // picker in the inspector is where that choice is made.
        if (payload?.kind === 'person') {
          void editor.onPlacePerson?.(payload.id, null)
        }
      }}
    >
      <header className="orgbox__head">
        <Icon name="members" size={14} />
        <span className="orgbox__title">{t('org.unplaced')}</span>
        <span className="muted">{t('org.peopleCount', { count: people.length })}</span>
      </header>
      <p className="orgbox__hint">{t('org.unplacedHint')}</p>
      <div className="orgbox__people">
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
      style={{ width: textWidth(node.name) + 28 }}
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
