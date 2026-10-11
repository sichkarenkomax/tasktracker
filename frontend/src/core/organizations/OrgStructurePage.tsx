import { useMemo, useRef, useState } from 'react'

import { useAsync, useMutation } from '../hooks/useAsync'
import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n'
import { Icon } from '../layout/Icon'
import { useCapabilities } from '../permissions/capabilities'
import { Listbox } from '../ui/Listbox'
import { Avatar } from '../users/Avatar'
import { PersonSelect } from '../users/PersonSelect'
import { flattenMember, organizationsApi } from './api'
import type { Member, OrgPosition, OrgStructure, Placement } from './api'
import { displayName, flattenDepartments } from './chartLayout'
import { DepartmentPopup } from './DepartmentPopup'
import { OrgChart } from './OrgChart'
import { useOrganizationId } from './OrganizationContext'
import { RequiresOrganization } from './RequiresOrganization'

/**
 * The organization: departments, positions and who reports to whom.
 *
 * Two views of one dataset. The chart is how the shape is read at a glance; the
 * list is how a specific fact is found, because "who is in Backend" is a lookup
 * and scrolling a chart to answer it is not.
 *
 * Editing happens in three places over the same payload: the chart for the
 * gestures (nest, place, report), an inspector per selected person or
 * department for the fields, and the editor panel for the directory of
 * departments and positions. Every write goes through the API and the whole
 * structure is reloaded afterwards rather than patched locally. The chart is a
 * graph; a locally patched graph is one accepted-but-rejected reparent away
 * from drawing something the server never stored.
 */
export function OrgStructurePage() {
  return (
    <RequiresOrganization>
      <OrgStructure />
    </RequiresOrganization>
  )
}

type View = 'chart' | 'list'

function OrgStructure() {
  const { t } = useI18n()
  const organizationId = useOrganizationId()
  const capabilities = useCapabilities(organizationId)
  const [view, setView] = useState<View>('chart')
  const [selected, setSelected] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  // Which department the popover is on, and what it hangs from. The anchor is
  // kept in a ref as well as in the state because Popover measures against the
  // live element on every scroll, and a stale copy in state would point at the
  // node the popover was opened from even after the chart redrew under it.
  const [departmentPopup, setDepartmentPopup] = useState<{
    departmentId: string | null
    parentId: string | null
  } | null>(null)
  const departmentAnchor = useRef<HTMLElement | null>(null)

  const structure = useAsync(
    () => (organizationId ? organizationsApi.structure(organizationId) : Promise.resolve(null)),
    [organizationId],
  )

  if (organizationId === null) return null

  const members = structure.data ? toMembers(structure.data) : []
  const mayEdit = capabilities.canEditOrgStructure
  const canEdit = mayEdit && editing

  /** One chart gesture: run it, then redraw from the server's answer. */
  const runAction = async (action: Promise<unknown>): Promise<void> => {
    setActionError(null)
    try {
      await action
      structure.reload()
    } catch (cause: unknown) {
      setActionError(cause instanceof Error ? cause.message : t('error.generic'))
    }
  }

  const selectPerson = (userId: string) => {
    setDepartmentPopup(null)
    setSelected((current) => (current === userId ? null : userId))
  }

  const openDepartment = (
    departmentId: string | null,
    parentId: string | null,
    anchor: HTMLElement,
  ) => {
    setSelected(null)
    departmentAnchor.current = anchor
    setDepartmentPopup((current) =>
      current?.departmentId === departmentId && current?.parentId === parentId
        ? null
        : { departmentId, parentId },
    )
  }

  return (
    <section className="org">
      <header className="page-header">
        <h1>{t('org.structure')}</h1>

        <div className="page-header__actions">
          <div className="tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={view === 'chart'}
              className={view === 'chart' ? 'tabs__tab tabs__tab--active' : 'tabs__tab'}
              onClick={() => setView('chart')}
            >
              {t('org.chart')}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === 'list'}
              className={view === 'list' ? 'tabs__tab tabs__tab--active' : 'tabs__tab'}
              onClick={() => setView('list')}
            >
              {t('org.list')}
            </button>
          </div>

          {mayEdit ? (
            <button
              type="button"
              className={editing ? 'button button--primary' : 'button button--ghost'}
              aria-pressed={editing}
              onClick={() => setEditing((value) => !value)}
            >
              <Icon name={editing ? 'check' : 'edit'} size={15} />
              {editing ? t('org.doneEditing') : t('org.editStructure')}
            </button>
          ) : null}
        </div>
      </header>

      {!mayEdit ? <p className="muted org__note">{t('org.readOnlyHint')}</p> : null}

      {structure.error ? (
        <p className="notice notice--error" role="alert">
          {structure.error}
        </p>
      ) : null}
      {actionError ? (
        <p className="notice notice--error" role="alert">
          {actionError}
        </p>
      ) : null}
      {structure.loading && !structure.data ? <p className="notice">{t('app.loading')}</p> : null}

      {structure.data ? (
        <>
          {canEdit ? (
            <StructureEditor
              structure={structure.data}
              onChanged={structure.reload}
              onSelectDepartment={(departmentId, anchor) => openDepartment(departmentId, null, anchor)}
              onAddDepartment={(anchor) => openDepartment(null, null, anchor)}
            />
          ) : null}

          {view === 'chart' ? (
            <OrgChart
              structure={structure.data}
              members={members}
              selectedUserId={selected}
              selectedDepartmentId={departmentPopup?.departmentId ?? null}
              editable={canEdit}
              onSelect={selectPerson}
              onSelectDepartment={(departmentId, anchor) => openDepartment(departmentId, null, anchor)}
              onAddDepartment={(parentId, anchor) => openDepartment(null, parentId, anchor)}
              onReparentDepartment={async (departmentId, parentId) => {
                await runAction(
                  organizationsApi.updateDepartment(organizationId, departmentId, {
                    parent_id: parentId,
                  }),
                )
              }}
              onReorderDepartment={async (departmentId, targetId, zone) => {
                // The chart is only rendered when there is data, but TypeScript
                // cannot see through the closure that a load has not raced.
                if (!structure.data) return
                await runAction(
                  reorder(organizationId, structure.data, departmentId, targetId, zone),
                )
              }}
              onPlacePerson={async (userId, departmentId) => {
                await runAction(
                  organizationsApi.placeMember(organizationId, userId, { department_id: departmentId }),
                )
              }}
              onAssignManager={async (userId, managerId) => {
                await runAction(
                  organizationsApi.placeMember(organizationId, userId, { manager_id: managerId }),
                )
              }}
              onGestureError={(message) => setActionError(message)}
            />
          ) : (
            <OrgList
              structure={structure.data}
              members={members}
              selectedUserId={selected}
              onSelect={selectPerson}
              canEdit={canEdit}
            />
          )}

          {departmentPopup && canEdit ? (
            <DepartmentPopup
              key={departmentPopup.departmentId ?? `new:${departmentPopup.parentId ?? 'root'}`}
              structure={structure.data}
              members={members}
              organizationId={organizationId}
              departmentId={departmentPopup.departmentId}
              parentId={departmentPopup.parentId}
              anchorRef={departmentAnchor}
              onChanged={structure.reload}
              onClose={() => setDepartmentPopup(null)}
            />
          ) : null}

          {selected ? (
            <PersonInspector
              structure={structure.data}
              members={members}
              userId={selected}
              canEdit={canEdit}
              onChanged={structure.reload}
              onClose={() => setSelected(null)}
            />
          ) : null}
        </>
      ) : null}
    </section>
  )
}

function toMembers(structure: OrgStructure): Member[] {
  return structure.members.map(flattenMember)
}

/**
 * Move a department next to another one, as siblings.
 *
 * The parent is settled first, then the order. The reverse would be rejected by
 * the server - the order endpoint insists on receiving exactly one group of
 * siblings, and a department that has just changed parents is not yet among the
 * target's.
 */
async function reorder(
  organizationId: string,
  structure: OrgStructure,
  departmentId: string,
  targetId: string,
  zone: 'before' | 'after',
): Promise<void> {
  const dragged = structure.departments.find((item) => item.id === departmentId)
  const target = structure.departments.find((item) => item.id === targetId)
  if (!dragged || !target) return

  if (dragged.parent_id !== target.parent_id) {
    await organizationsApi.updateDepartment(organizationId, departmentId, {
      parent_id: target.parent_id,
    })
  }

  // The row the department will sit in, once it belongs there.
  const siblings = structure.departments
    .filter((item) => item.parent_id === target.parent_id)
    .sort((left, right) => left.position - right.position)

  const next = siblings.filter((item) => item.id !== departmentId)
  const at = next.findIndex((item) => item.id === targetId)
  if (at === -1) return
  next.splice(zone === 'before' ? at : at + 1, 0, dragged)

  await organizationsApi.reorderDepartments(
    organizationId,
    next.map((item) => item.id),
  )
}

/**
 * The list.
 *
 * Indented by reporting line rather than by department: "who does this person
 * manage" is the question the chart answers visually and this answers exactly,
 * one row per person, with their department beside them as a column.
 */
function OrgList({
  structure,
  members,
  selectedUserId,
  onSelect,
  canEdit,
}: {
  structure: OrgStructure
  members: Member[]
  selectedUserId: string | null
  onSelect: (userId: string) => void
  canEdit: boolean
}) {
  const { t } = useI18n()

  // Only the chart can open the inspector on a click; here a click just selects
  // the row, because a row is already the whole record.

  const rows = useMemo(
    () => flattenByReporting(structure.placements, members),
    [structure.placements, members],
  )
  const departmentsById = useMemo(
    () => new Map(structure.departments.map((department) => [department.id, department])),
    [structure.departments],
  )
  const positionsById = useMemo(
    () => new Map(structure.positions.map((position) => [position.id, position])),
    [structure.positions],
  )

  if (rows.length === 0) {
    return <p className="notice">{t('org.chartEmpty')}</p>
  }

  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">{t('org.people')}</th>
            <th scope="col">{t('org.positionTitle')}</th>
            <th scope="col">{t('org.departments')}</th>
            <th scope="col">{t('org.reportsTo')}</th>
            <th scope="col">{t('org.deputies')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const placement = structure.placements[row.userId]
            const department = placement?.department_id
              ? departmentsById.get(placement.department_id)
              : undefined
            const position = placement?.position_id
              ? positionsById.get(placement.position_id)
              : undefined

            return (
              <tr
                key={row.userId}
                className={selectedUserId === row.userId ? 'table__row--selected' : undefined}
              >
                <td>
                  <button
                    type="button"
                    className={canEdit ? 'orglist__name' : 'orglist__name orglist__name--static'}
                    style={{ paddingInlineStart: `${row.depth * 1.25 + 0.5}rem` }}
                    onClick={() => onSelect(row.userId)}
                  >
                    {row.depth > 0 ? (
                      <span className="orglist__branch" aria-hidden="true">
                        ↳
                      </span>
                    ) : null}
                    {row.name}
                  </button>
                </td>
                <td>{position?.title ?? <span className="muted">{t('org.noPosition')}</span>}</td>
                <td>
                  {department?.name ?? <span className="muted">{t('org.noDepartment')}</span>}
                </td>
                <td>
                  {placement?.manager_id ? (
                    nameOf(members, placement.manager_id)
                  ) : (
                    <span className="muted">{t('org.noManager')}</span>
                  )}
                </td>
                <td>
                  {(placement?.deputies ?? []).length === 0 ? (
                    <span className="muted">—</span>
                  ) : (
                    (placement?.deputies ?? []).map((id) => nameOf(members, id)).join(', ')
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function nameOf(members: Member[], userId: string): string {
  const member = members.find((item) => item.user_id === userId)
  return member ? displayName(member) : userId
}

interface FlatRow {
  userId: string
  name: string
  depth: number
}

/**
 * Reporting lines, flattened into a list with a depth.
 *
 * People with no manager come first, in name order, then each person's reports
 * under them. A cycle cannot reach this function - the server refuses to write
 * one - but the visited set is here anyway, because a chart that hangs on one
 * stuck node is worse than a chart that quietly omits it.
 */
function flattenByReporting(placements: Record<string, Placement>, members: Member[]): FlatRow[] {
  const rows: FlatRow[] = []
  const visited = new Set<string>()

  const reports = new Map<string, string[]>()
  for (const member of members) {
    const managerId = placements[member.user_id]?.manager_id ?? null
    if (!managerId) continue
    const list = reports.get(managerId) ?? []
    list.push(member.user_id)
    reports.set(managerId, list)
  }
  for (const list of reports.values()) list.sort()

  const roots = members
    .filter((member) => !placements[member.user_id]?.manager_id)
    .map((member) => member.user_id)
    .sort()

  const walk = (userId: string, depth: number) => {
    if (visited.has(userId)) return
    visited.add(userId)
    const member = members.find((item) => item.user_id === userId)
    rows.push({ userId, name: member ? displayName(member) : userId, depth })
    for (const child of reports.get(userId) ?? []) walk(child, depth + 1)
  }

  for (const root of roots) walk(root, 0)

  // Anything the walk did not reach would otherwise disappear from the list.
  for (const member of members) walk(member.user_id, 0)
  return rows
}

/**
 * The directory of departments and positions.
 *
 * Departments are drawn with their nesting visible and every row opens the
 * inspector, because the row is where somebody noticed the department was
 * wrong. Positions are edited in place: a title, a rank and a scope are three
 * short facts, and a form per position would triple the clicks to fix one.
 */
function StructureEditor({
  structure,
  onChanged,
  onSelectDepartment,
  onAddDepartment,
}: {
  structure: OrgStructure
  onChanged: () => void
  onSelectDepartment: (departmentId: string, anchor: HTMLElement) => void
  onAddDepartment: (anchor: HTMLElement) => void
}) {
  const { t } = useI18n()
  const organizationId = useOrganizationId()
  const [adding, setAdding] = useState<'position' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const addPosition = useMutation<string, void>(async (title) => {
    if (!organizationId) return
    await organizationsApi.createPosition(organizationId, { title })
  })

  const removeDepartment = useMutation<string, void>(async (id) => {
    if (!organizationId) return
    await organizationsApi.deleteDepartment(organizationId, id)
  })

  const removePosition = useMutation<string, void>(async (id) => {
    if (!organizationId) return
    await organizationsApi.deletePosition(organizationId, id)
  })

  const report = (cause: unknown) => {
    setError(cause instanceof Error ? cause.message : t('error.generic'))
  }

  const failing =
    error ??
    addPosition.error ??
    removeDepartment.error ??
    removePosition.error

  const departmentRows = flattenDepartments(structure.departments)

  return (
    <section className="panel org__editor">
      <div className="org__editor-col">
        <h2>{t('org.departments')}</h2>
        {/* Opens the same popover the pencil opens, with the name empty: a second
            form for "add a department" would be a second answer to what one is. */}
        <button
          type="button"
          className="button button--ghost"
          onClick={(event) => onAddDepartment(event.currentTarget)}
        >
          <Icon name="plus" size={14} />
          {t('org.addDepartment')}
        </button>

        <ul className="org__list">
          {departmentRows.map(({ department, depth }) => (
            <li key={department.id} style={{ paddingInlineStart: `${depth * 0.9 + 0.4}rem` }}>
              <button
                type="button"
                className="orglist__name"
                onClick={(event) => onSelectDepartment(department.id, event.currentTarget)}
              >
                {depth > 0 ? (
                  <span className="orglist__branch" aria-hidden="true">
                    ↳
                  </span>
                ) : null}
                {department.name}
              </button>
              <button
                type="button"
                className="icon-button"
                aria-label={`${t('org.deleteDepartment')}: ${department.name}`}
                onClick={() => {
                  if (
                    !window.confirm(t('org.deleteDepartmentConfirm', { name: department.name }))
                  ) {
                    return
                  }
                  setError(null)
                  void removeDepartment.runOrThrow(department.id).then(onChanged).catch(report)
                }}
              >
                <Icon name="trash" size={13} />
              </button>
            </li>
          ))}
        </ul>
        {structure.departments.length === 0 ? (
          <p className="muted">{t('org.departmentEmpty')}</p>
        ) : null}
      </div>

      <div className="org__editor-col">
        <h2>{t('org.positions')}</h2>
        <button
          type="button"
          className="button button--ghost"
          onClick={() => setAdding((value) => (value === 'position' ? null : 'position'))}
        >
          <Icon name="plus" size={14} />
          {t('org.addPosition')}
        </button>

        {adding === 'position' ? (
          <NameForm
            label={t('org.positionTitle')}
            submitLabel={t('app.create')}
            pending={addPosition.pending}
            onSubmit={async (title) => {
              setError(null)
              const done = await addPosition.run(title)
              if (done !== null) {
                setAdding(null)
                onChanged()
              }
            }}
          />
        ) : null}

        <ul className="org__list org__list--positions">
          {structure.positions.map((position) => (
            <PositionRow
              key={position.id}
              structure={structure}
              position={position}
              onChanged={onChanged}
              onError={report}
            />
          ))}
        </ul>
        {structure.positions.length === 0 ? (
          <p className="muted">{t('org.positionEmpty')}</p>
        ) : null}
      </div>

      {failing ? (
        <p className="notice notice--error" role="alert">
          {failing}
        </p>
      ) : null}
    </section>
  )
}

/**
 * One position, edited in place.
 *
 * The title and the rank are committed on blur rather than per keystroke: a
 * rank is a number somebody types one digit at a time, and one request per
 * digit would reload the structure from under their cursor.
 */
function PositionRow({
  structure,
  position,
  onChanged,
  onError,
}: {
  structure: OrgStructure
  position: OrgPosition
  onChanged: () => void
  onError: (cause: unknown) => void
}) {
  const { t } = useI18n()
  const organizationId = useOrganizationId()
  const [title, setTitle] = useState(position.title)
  const [rank, setRank] = useState(position.rank === null ? '' : String(position.rank))

  const save = async (body: {
    title?: string
    rank?: number | null
    department_id?: string | null
  }) => {
    if (!organizationId) return
    try {
      await organizationsApi.updatePosition(organizationId, position.id, body)
      onChanged()
    } catch (cause: unknown) {
      onError(cause)
    }
  }

  return (
    <li className="org__position">
      <input
        className="org__position-title"
        aria-label={t('org.positionTitle')}
        maxLength={200}
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        onBlur={() => {
          const trimmed = title.trim()
          if (!trimmed || trimmed === position.title) {
            setTitle(position.title)
            return
          }
          void save({ title: trimmed })
        }}
      />
      <input
        className="org__position-rank"
        type="number"
        aria-label={t('org.rank')}
        title={t('org.rankHint')}
        value={rank}
        onChange={(event) => setRank(event.target.value)}
        onBlur={() => {
          const trimmed = rank.trim()
          const next = trimmed === '' ? null : Number(trimmed)
          if (next === position.rank || (next === null && position.rank === null)) return
          if (next !== null && !Number.isFinite(next)) return
          void save({ rank: next })
        }}
      />
      <Listbox<string>
        className="org__position-dept"
        aria-label={t('org.positionDepartment')}
        value={position.department_id ?? null}
        options={structure.departments.map((department) => ({
          value: department.id,
          label: department.name,
        }))}
        placeholder={t('org.noDepartment')}
        clearable
        onChange={(next) => void save({ department_id: next ?? null })}
      />
      <button
        type="button"
        className="icon-button"
        aria-label={`${t('org.deletePosition')}: ${position.title}`}
        onClick={() => {
          if (!organizationId) return
          if (!window.confirm(t('org.deletePositionConfirm', { title: position.title }))) return
          void organizationsApi
            .deletePosition(organizationId, position.id)
            .then(onChanged)
            .catch(onError)
        }}
      >
        <Icon name="trash" size={13} />
      </button>
    </li>
  )
}

function NameForm({
  label,
  submitLabel,
  pending,
  onSubmit,
}: {
  label: string
  submitLabel: string
  pending: boolean
  onSubmit: (value: string) => Promise<void>
}) {
  const { t } = useI18n()
  const [value, setValue] = useState('')

  return (
    <form
      className="inline-form"
      onSubmit={async (event) => {
        event.preventDefault()
        const trimmed = value.trim()
        if (!trimmed) return
        await onSubmit(trimmed)
        setValue('')
      }}
    >
      <label className="field">
        <span>{label}</span>
        <input
          autoFocus
          maxLength={200}
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
      </label>
      <div className="create-form__actions">
        <button type="submit" className="button button--primary" disabled={pending || !value.trim()}>
          {pending ? t('app.saving') : submitLabel}
        </button>
      </div>
    </form>
  )
}

/**
 * One person's placement, in full.
 *
 * Every control writes immediately and independently. That is deliberate: the
 * fields do not depend on each other, and a form with one Save would make
 * changing a manager a three-step operation for no gain.
 */
function PersonInspector({
  structure,
  members,
  userId,
  canEdit,
  onChanged,
  onClose,
}: {
  structure: OrgStructure
  members: Member[]
  userId: string
  canEdit: boolean
  onChanged: () => void
  onClose: () => void
}) {
  const { t } = useI18n()
  const organizationId = useOrganizationId()
  const [error, setError] = useState<string | null>(null)

  const member = members.find((item) => item.user_id === userId)
  const placement = structure.placements[userId]

  const place = useMutation<
    { department_id?: string | null; position_id?: string | null; manager_id?: string | null },
    void
  >(async (body) => {
    if (!organizationId) return
    await organizationsApi.placeMember(organizationId, userId, body)
  })

  const addDeputy = useMutation<string, void>(async (deputyId) => {
    if (!organizationId) return
    await organizationsApi.addDeputy(organizationId, userId, deputyId)
  })

  const removeDeputy = useMutation<string, void>(async (deputyId) => {
    if (!organizationId) return
    await organizationsApi.removeDeputy(organizationId, userId, deputyId)
  })

  if (!member || !placement) return null

  // Everybody except this person: the server refuses the rest, but offering them
  // would fill the list with choices that always fail.
  const candidates = members.filter((item) => item.user_id !== userId)
  const deputyCandidates = candidates.filter((item) => !placement.deputies.includes(item.user_id))

  const run = async (action: Promise<unknown>) => {
    setError(null)
    try {
      await action
      onChanged()
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : t('error.generic'))
    }
  }

  return (
    <section className="panel org__inspector">
      <header className="org__inspector-head">
        <Avatar src={member.avatar_url} name={displayName(member)} size="sm" />
        <div>
          <strong>{displayName(member)}</strong>
          <span className="muted">{member.email}</span>
        </div>
        <button type="button" className="icon-button" aria-label={t('app.cancel')} onClick={onClose}>
          <Icon name="close" size={14} />
        </button>
      </header>

      <div className="fields">
        <label className="field">
          <span>{t('org.departments')}</span>
          <Listbox<string>
            value={placement.department_id ?? null}
            options={structure.departments.map((department) => ({
              value: department.id,
              label: department.name,
            }))}
            placeholder={t('org.noDepartment')}
            clearable
            disabled={!canEdit || place.pending}
            onChange={(next) => void run(place.runOrThrow({ department_id: next ?? null }))}
          />
        </label>

        <label className="field">
          <span>{t('org.positions')}</span>
          <Listbox<string>
            value={placement.position_id ?? null}
            options={structure.positions.map((position) => ({
              value: position.id,
              label: position.title,
            }))}
            placeholder={t('org.noPosition')}
            clearable
            disabled={!canEdit || place.pending}
            onChange={(next) => void run(place.runOrThrow({ position_id: next ?? null }))}
          />
        </label>

        <label className="field">
          <span>{t('org.manager')}</span>
          <PersonSelect
            members={candidates}
            value={placement.manager_id ?? null}
            placeholder={t('org.noManager')}
            clearable
            disabled={!canEdit || place.pending}
            onChange={(next) => void run(place.runOrThrow({ manager_id: next ?? null }))}
          />
        </label>
      </div>

      <div className="org__deputies">
        <h3>{t('org.deputies')}</h3>
        {placement.deputies.length === 0 ? (
          <p className="muted">{t('org.noDeputy')}</p>
        ) : (
          <ul className="org__list">
            {placement.deputies.map((deputyId) => (
              <li key={deputyId}>
                <span>{nameOf(members, deputyId)}</span>
                {canEdit ? (
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`${t('org.deputy')}: ${nameOf(members, deputyId)}`}
                    disabled={removeDeputy.pending}
                    onClick={() => void run(removeDeputy.runOrThrow(deputyId))}
                  >
                    <Icon name="close" size={13} />
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}

        {canEdit && deputyCandidates.length > 0 ? (
          <PersonSelect
            members={deputyCandidates}
            value={null}
            placeholder={t('org.addDeputy')}
            aria-label={t('org.addDeputy')}
            onChange={(next) => {
              if (next) void run(addDeputy.runOrThrow(next))
            }}
          />
        ) : null}
      </div>

      {error ? (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  )
}

export { flattenByReporting }
export type { TranslationKey }
