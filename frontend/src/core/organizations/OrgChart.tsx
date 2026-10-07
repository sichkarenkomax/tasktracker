import { useMemo } from 'react'

import { useI18n } from '../i18n'
import { Icon } from '../layout/Icon'
import type { Member, OrgPosition, OrgStructure } from './api'
import { buildChart, textWidth } from './chartLayout'
import type { ChartGroup, ChartNode } from './chartLayout'

/**
 * The org chart: departments as boxes, people inside them.
 *
 * Read-only by design. Dragging a person from one box to another on a canvas is
 * one mis-click away from a chart nobody trusts, and every move here is instead an
 * explicit choice in the inspector beside the chart, where the current value is
 * visible and the change can be undone by choosing it again.
 *
 * Departments rather than a flat row of people joined by lines: Engineering
 * containing Backend is half of what an org chart is for, and a flat row cannot
 * show it.
 */
export function OrgChart({
  structure,
  members,
  onSelect,
  selectedUserId,
}: {
  structure: OrgStructure
  members: Member[]
  onSelect: (userId: string) => void
  selectedUserId: string | null
}) {
  const { t } = useI18n()

  const positionsById = useMemo(
    () => new Map(structure.positions.map((position) => [position.id, position])),
    [structure.positions],
  )

  const chart = useMemo(
    () => buildChart(structure.departments, members, structure.placements),
    [structure.departments, members, structure.placements],
  )

  if (chart.roots.length === 0 && chart.unplaced.length === 0) {
    return <p className="notice">{t('org.chartEmpty')}</p>
  }

  return (
    <div className="orgchart">
      {chart.roots.map((group) => (
        <DepartmentBox
          key={group.departmentId}
          group={group}
          depth={0}
          positionsById={positionsById}
          structure={structure}
          members={members}
          selectedUserId={selectedUserId}
          onSelect={onSelect}
        />
      ))}

      {chart.unplaced.length > 0 ? (
        <section className="orgbox orgbox--unplaced" aria-label={t('org.unplaced')}>
          <header className="orgbox__head">
            <Icon name="members" size={14} />
            <span className="orgbox__title">{t('org.unplaced')}</span>
            <span className="muted">{t('org.peopleCount', { count: chart.unplaced.length })}</span>
          </header>
          <p className="orgbox__hint">{t('org.unplacedHint')}</p>
          <div className="orgbox__people">
            {chart.unplaced.map((person) => (
              <PersonCard
                key={person.userId}
                node={person}
                title={titleOf(person, positionsById)}
                selected={selectedUserId === person.userId}
                onSelect={onSelect}
              />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  )
}

/** The position title to draw on a card, or null when they hold none. */
function titleOf(person: ChartNode, positions: Map<string, OrgPosition>): string | null {
  if (!person.positionId) return null
  return positions.get(person.positionId)?.title ?? null
}

function DepartmentBox({
  group,
  depth,
  positionsById,
  structure,
  members,
  selectedUserId,
  onSelect,
}: {
  group: ChartGroup
  depth: number
  positionsById: Map<string, OrgPosition>
  structure: OrgStructure
  members: Member[]
  selectedUserId: string | null
  onSelect: (userId: string) => void
}) {
  const { t } = useI18n()

  const nameOf = (userId: string): string => {
    const member = members.find((item) => item.user_id === userId)
    return member ? member.first_name || member.username : t('activity.someone')
  }

  return (
    <section
      className="orgbox"
      style={{ marginInlineStart: `${depth * 1.5}rem` }}
      aria-label={group.name}
    >
      <header className="orgbox__head">
        <Icon name="projects" size={14} />
        <span className="orgbox__title">{group.name}</span>
        {group.headId ? (
          <span className="orgbox__head-name">{nameOf(group.headId)}</span>
        ) : null}
        <span className="muted">{t('org.peopleCount', { count: group.people.length })}</span>
      </header>

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
              structure={structure}
              members={members}
              selectedUserId={selectedUserId}
              onSelect={onSelect}
            />
          ))}
        </div>
      ) : null}
    </section>
  )
}

function PersonCard({
  node,
  title,
  deputyCount = 0,
  selected,
  onSelect,
}: {
  node: ChartNode
  title: string | null
  deputyCount?: number
  selected: boolean
  onSelect: (userId: string) => void
}) {
  const { t } = useI18n()

  return (
    <button
      type="button"
      className={selected ? 'orgperson orgperson--selected' : 'orgperson'}
      style={{ width: textWidth(node.name) + 28 }}
      onClick={() => onSelect(node.userId)}
      aria-pressed={selected}
    >
      <span className="orgperson__avatar" aria-hidden="true">
        {node.name.charAt(0).toUpperCase()}
      </span>
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
