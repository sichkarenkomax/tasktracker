import { useEffect, useState } from 'react'

import { useMutation } from '../hooks/useAsync'
import { useI18n } from '../i18n'
import { Icon } from '../layout/Icon'
import { Listbox } from '../ui/Listbox'
import { Popover } from '../ui/Popover'
import { PersonSelect } from '../users/PersonSelect'
import { organizationsApi } from './api'
import type { Member, OrgStructure } from './api'
import { departmentSubtree, memberName } from './chartLayout'

/**
 * One department, in full (2.15).
 *
 * A popover on the department's own button rather than a panel under the chart.
 * The panel was three things at once and none of them fit: it took the bottom of
 * the screen away from a chart the reader was still working on, it appeared for
 * one department while sitting under all of them, and adding a department used a
 * different form in a different place, so "what a department is" was written down
 * twice in two shapes.
 *
 * Same department, same fields, whether it already exists or not - which is what
 * makes the "+" and the pencil the same thing with one field filled in.
 *
 * Every control writes on its own and immediately, like the person inspector
 * beside it. The alternative - one Save button over five fields - turns one
 * refused request into five lost edits.
 */
export interface DepartmentPopupProps {
  structure: OrgStructure
  members: Member[]
  organizationId: string
  /** Null opens it on "new department", under this parent. */
  departmentId: string | null
  parentId: string | null
  anchorRef: React.RefObject<HTMLElement | null>
  onChanged: () => void
  onClose: () => void
}

export function DepartmentPopup({
  structure,
  members,
  organizationId,
  departmentId,
  parentId,
  anchorRef,
  onChanged,
  onClose,
}: DepartmentPopupProps) {
  const { t } = useI18n()
  const [error, setError] = useState<string | null>(null)

  const department = departmentId ? structure.departments.find((item) => item.id === departmentId) : undefined
  const creating = departmentId === null

  const [name, setName] = useState(department?.name ?? '')
  const [description, setDescription] = useState(department?.description ?? '')

  const rename = useMutation<string, void>(async (next) => {
    await organizationsApi.updateDepartment(organizationId, departmentId as string, { name: next })
  })
  const setDescriptionText = useMutation<string | null, void>(async (next) => {
    await organizationsApi.updateDepartment(organizationId, departmentId as string, { description: next })
  })
  const setParent = useMutation<string | null, void>(async (next) => {
    await organizationsApi.updateDepartment(organizationId, departmentId as string, { parent_id: next })
  })
  const setHead = useMutation<string | null, void>(async (next) => {
    await organizationsApi.updateDepartment(organizationId, departmentId as string, { head_id: next })
  })
  const addDeputy = useMutation<string, void>(async (deputyId) => {
    await organizationsApi.addDepartmentDeputy(organizationId, departmentId as string, deputyId)
  })
  const removeDeputy = useMutation<string, void>(async (deputyId) => {
    await organizationsApi.removeDepartmentDeputy(organizationId, departmentId as string, deputyId)
  })
  const place = useMutation<string, void>(async (userId) => {
    await organizationsApi.placeMember(organizationId, userId, { department_id: departmentId })
  })
  const unplace = useMutation<string, void>(async (userId) => {
    await organizationsApi.placeMember(organizationId, userId, { department_id: null })
  })
  const remove = useMutation<null, void>(async () => {
    await organizationsApi.deleteDepartment(organizationId, departmentId as string)
  })
  const create = useMutation<string, string>(async (newName) => {
    const made = await organizationsApi.createDepartment(organizationId, {
      name: newName,
      description: description.trim() || null,
      parent_id: parentId,
    })
    onChanged()
    // Open the same panel on what was just created rather than closing it: the
    // name was the only thing written, and the next thing anybody does is set
    // the head or the deputy.
    onClose()
    return made.id
  })

  // A department that was deleted while this panel was open (another tab, the
  // editor panel's trash) would otherwise leave its controls writing to nothing.
  useEffect(() => {
    if (departmentId !== null && !department) onClose()
  }, [departmentId, department, onClose])

  const run = async (action: Promise<unknown>) => {
    setError(null)
    try {
      await action
      onChanged()
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : t('error.generic'))
    }
  }

  const deputyIds = departmentId ? (structure.department_deputies[departmentId] ?? []) : []
  const headId = department?.head_id ?? null

  // The head already runs the department; offering them as their own deputy
  // would be a second answer to a question head_id already answers, and the
  // server refuses it.
  const deputyCandidates = members.filter(
    (item) => !deputyIds.includes(item.user_id) && item.user_id !== headId,
  )

  const rosterIds = structure.members
    .filter((member) => structure.placements[member.user_id]?.department_id === departmentId)
    .map((member) => member.user_id)

  const joinable = members.filter((item) => !rosterIds.includes(item.user_id))

  const saveName = () => {
    const trimmed = name.trim()
    if (creating) return
    if (!trimmed || trimmed === department?.name) {
      setName(department?.name ?? '')
      return
    }
    void run(rename.runOrThrow(trimmed))
  }

  const saveDescription = () => {
    if (creating) return
    const trimmed = description.trim()
    if (trimmed === (department?.description ?? '')) return
    // null clears it, an absent key would leave it alone: an empty textarea the
    // reader deliberately emptied has to save as "no description".
    void run(setDescriptionText.runOrThrow(trimmed || null))
  }

  const body = (
    <>
      <label className="field">
        <span>{t('org.departmentName')}</span>
        <input
          maxLength={200}
          value={name}
          placeholder={t('org.departmentNamePlaceholder')}
          onChange={(event) => setName(event.target.value)}
          onBlur={creating ? undefined : saveName}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              if (creating) void run(create.runOrThrow(name.trim()))
              else saveName()
            }
          }}
        />
      </label>

      <label className="field">
        <span>{t('org.departmentDescription')}</span>
        <textarea
          className="input"
          rows={2}
          maxLength={2000}
          value={description}
          placeholder={t('org.departmentDescriptionPlaceholder')}
          onChange={(event) => setDescription(event.target.value)}
          onBlur={creating ? undefined : saveDescription}
        />
      </label>

      {creating ? (
        <label className="field">
          <span>{t('org.parent')}</span>
          <Listbox<string>
            value={parentId}
            options={structure.departments.map((item) => ({ value: item.id, label: item.name }))}
            placeholder={t('org.topLevel')}
            clearable
            onChange={() => {
              /* The parent of a department that does not exist yet is fixed by
                 the "+" that opened this panel; changing it here would move the
                 parent instead of the child. */
            }}
          />
        </label>
      ) : (
        <>
          <label className="field">
            <span>{t('org.parent')}</span>
            <Listbox<string>
              value={department?.parent_id ?? null}
              options={structure.departments
                // The department's own subtree cannot be its parent: the server
                // refuses that move, and offering it would make the chart look
                // broken rather than refused.
                .filter((item) => !departmentSubtree(structure.departments, departmentId).has(item.id))
                .map((item) => ({ value: item.id, label: item.name }))}
              placeholder={t('org.topLevel')}
              clearable
              disabled={setParent.pending}
              onChange={(next) => void run(setParent.runOrThrow(next ?? null))}
            />
          </label>

          <label className="field">
            <span>{t('org.head')}</span>
            <PersonSelect
              members={members}
              value={headId}
              placeholder={t('org.noManager')}
              clearable
              disabled={setHead.pending}
              onChange={(next) => void run(setHead.runOrThrow(next ?? null))}
            />
          </label>

          <section className="department-popup__block">
            <h3>{t('org.departmentDeputy')}</h3>
            {deputyIds.length === 0 ? (
              <p className="muted">{t('org.noDeputy')}</p>
            ) : (
              <ul className="org__list">
                {deputyIds.map((deputyId) => (
                  <li key={deputyId}>
                    <span>{memberName(members, deputyId) ?? t('activity.someone')}</span>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`${t('org.removeDeputy')}: ${memberName(members, deputyId) ?? t('activity.someone')}`}
                      disabled={removeDeputy.pending}
                      onClick={() => void run(removeDeputy.runOrThrow(deputyId))}
                    >
                      <Icon name="close" size={13} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {deputyCandidates.length > 0 ? (
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
          </section>

          <section className="department-popup__block">
            <h3>{t('org.departmentMembers')}</h3>
            {rosterIds.length === 0 ? (
              <p className="muted">{t('org.departmentEmpty')}</p>
            ) : (
              <ul className="org__list">
                {rosterIds.map((userId) => (
                  <li key={userId}>
                    <span>{memberName(members, userId) ?? t('activity.someone')}</span>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`${t('org.removeFromDepartment')}: ${memberName(members, userId) ?? t('activity.someone')}`}
                      disabled={unplace.pending}
                      onClick={() => void run(unplace.runOrThrow(userId))}
                    >
                      <Icon name="close" size={13} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {joinable.length > 0 ? (
              <PersonSelect
                members={joinable}
                value={null}
                placeholder={t('org.addToDepartment')}
                aria-label={t('org.addToDepartment')}
                onChange={(next) => {
                  if (next) void run(place.runOrThrow(next))
                }}
              />
            ) : null}
          </section>
        </>
      )}

      {error ? (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      ) : null}

      {creating ? (
        <div className="department-popup__actions">
          <button type="button" className="button button--ghost" onClick={onClose}>
            {t('app.cancel')}
          </button>
          <button
            type="button"
            className="button button--primary"
            disabled={create.pending || name.trim() === ''}
            onClick={() => void run(create.runOrThrow(name.trim()))}
          >
            {t('app.create')}
          </button>
        </div>
      ) : (
        <div className="department-popup__actions department-popup__actions--split">
          <button
            type="button"
            className="button button--ghost button--danger"
            disabled={remove.pending}
            onClick={() => {
              // The button says what happens to the people, because "delete" on a
              // unit is otherwise read as deleting its staff.
              if (!window.confirm(t('org.deleteDepartmentConfirm', { name: department?.name ?? '' }))) {
                return
              }
              void run(
                remove.runOrThrow(null).then(() => {
                  onClose()
                }),
              )
            }}
          >
            <Icon name="trash" size={14} />
            {t('org.deleteDepartment')}
          </button>
          <button type="button" className="button button--ghost" onClick={onClose}>
            {t('app.close')}
          </button>
        </div>
      )}
    </>
  )

  return (
    <Popover
      open
      anchorRef={anchorRef}
      onClose={onClose}
      className="department-popup"
      labelledBy={undefined}
    >
      <header className="department-popup__head">
        <strong>{creating ? t('org.addDepartment') : t('org.departmentSettings')}</strong>
        <button type="button" className="icon-button" aria-label={t('app.close')} onClick={onClose}>
          <Icon name="close" size={14} />
        </button>
      </header>
      {body}
    </Popover>
  )
}