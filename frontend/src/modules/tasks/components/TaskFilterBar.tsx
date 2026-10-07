import { useEffect, useState } from 'react'

import { useI18n } from '../../../core/i18n'
import { Icon } from '../../../core/layout/Icon'
import type { Member } from '../../../core/organizations/api'
import { useTaskVocabulary } from './Badges'
import type { Project } from '../../../core/projects/api'
import {
  readSavedFilters,
  removeSavedFilter,
  upsertSavedFilter,
  writeSavedFilters,
} from './savedFilters'
import type { SavedFilter } from './savedFilters'
import { TASK_PRIORITIES, TASK_STATUSES } from '../types'
import type { TaskFilters, TaskPriority, TaskStatus, TranslationKey } from '../types'

/**
 * A filter a person can pin to the bar.
 *
 * Pins are stored by *name* rather than by a filter object, because the object is
 * only meaningful to this code version while the name stays meaningful across
 * upgrades - and because a pin has to be serialisable into the URL and back.
 */
export type QuickFilterId = 'status' | 'priority' | 'assignee' | 'project' | 'overdue'

export const QUICK_FILTERS: ReadonlyArray<{ id: QuickFilterId; label: TranslationKey }> = [
  { id: 'status', label: 'filters.byStatus' },
  { id: 'priority', label: 'filters.byPriority' },
  { id: 'assignee', label: 'filters.byAssignee' },
  { id: 'project', label: 'columns.column.project' },
  { id: 'overdue', label: 'filters.overdue' },
]

const STORAGE_KEY = 'tasktracker.quickFilters'

/**
 * Which filters a person pinned, in the order they pinned them.
 *
 * Read defensively: a value written by an older build - or edited by hand - may
 * name a filter that no longer exists, and an unknown name is dropped rather than
 * rendered as a control that does nothing.
 */
export function readQuickFilters(): QuickFilterId[] {
  const known = new Set(QUICK_FILTERS.map((entry) => entry.id))
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return ['status', 'assignee', 'overdue']
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return ['status', 'assignee', 'overdue']
    return parsed.filter((id): id is QuickFilterId => typeof id === 'string' && known.has(id as QuickFilterId))
  } catch {
    return ['status', 'assignee', 'overdue']
  }
}

export function writeQuickFilters(ids: QuickFilterId[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
  } catch {
    /* preference only */
  }
}

/**
 * The filter bar.
 *
 * Two tiers, because one flat row of every filter is unusable once there are six
 * of them: a handful the person uses daily sit on the bar as chips that can be
 * switched off in one click, and everything else lives behind "more filters".
 * The layout bug this replaces was one group wrapping mid-row and pushing the
 * rest of the bar down.
 *
 * State still lives in the URL. The bar only edits it.
 */
export interface TaskFilterBarProps {
  value: TaskFilters
  members: Member[]
  projects: Project[]
  onChange: (next: TaskFilters) => void
}

const SORTABLE: ReadonlyArray<{ id: string; label: TranslationKey }> = [
  { id: 'created_at', label: 'filters.sort.created_at' },
  { id: 'updated_at', label: 'filters.sort.updated_at' },
  { id: 'due_date', label: 'filters.sort.due_date' },
  { id: 'title', label: 'filters.sort.title' },
  { id: 'priority', label: 'filters.sort.priority' },
  { id: 'status', label: 'filters.sort.status' },
]

export function TaskFilterBar({ value, members, projects, onChange }: TaskFilterBarProps) {
  const { t } = useI18n()
  const { statusLabel, priorityLabel } = useTaskVocabulary()

  // The text box is local state so that typing does not fire a request per
  // keystroke; the value is committed on submit or on blur.
  const [term, setTerm] = useState(value.search ?? '')
  const [moreOpen, setMoreOpen] = useState(false)
  const [pins, setPins] = useState<QuickFilterId[]>(readQuickFilters)
  const [saved, setSaved] = useState<SavedFilter[]>(readSavedFilters)
  const [savingAs, setSavingAs] = useState(false)
  const [savedName, setSavedName] = useState('')
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => setTerm(value.search ?? ''), [value.search])

  function commitSearch() {
    const trimmed = term.trim()
    if ((value.search ?? '') === (trimmed || undefined)) return
    onChange({ ...value, search: trimmed || undefined })
  }

  function toggleStatus(status: TaskStatus) {
    const current = value.status ?? []
    const next = current.includes(status)
      ? current.filter((item) => item !== status)
      : [...current, status]
    onChange({ ...value, status: next.length ? next : undefined })
  }

  function togglePriority(priority: TaskPriority) {
    const current = value.priority ?? []
    const next = current.includes(priority)
      ? current.filter((item) => item !== priority)
      : [...current, priority]
    onChange({ ...value, priority: next.length ? next : undefined })
  }

  function setPin(id: QuickFilterId, pinned: boolean) {
    const next = pinned ? [...pins, id] : pins.filter((item) => item !== id)
    setPins(next)
    writeQuickFilters(next)
  }

  const selectedStatuses = value.status ?? []
  const selectedPriorities = value.priority ?? []

  const activeCount =
    selectedStatuses.length +
    selectedPriorities.length +
    (value.assignee_id ? 1 : 0) +
    (value.project_id ? 1 : 0) +
    (value.overdue ? 1 : 0) +
    (value.unfiled ? 1 : 0) +
    (value.search ? 1 : 0)

  function renderPinned(id: QuickFilterId): React.ReactNode {
    switch (id) {
      case 'status':
        return (
          <fieldset key="status" className="filter-group">
            <legend>{t('filters.byStatus')}</legend>
            {TASK_STATUSES.map((status) => (
              <label key={status} className="chip">
                <input
                  type="checkbox"
                  checked={selectedStatuses.includes(status)}
                  onChange={() => toggleStatus(status)}
                />
                {statusLabel(status)}
              </label>
            ))}
          </fieldset>
        )
      case 'priority':
        return (
          <fieldset key="priority" className="filter-group">
            <legend>{t('filters.byPriority')}</legend>
            {TASK_PRIORITIES.map((priority) => (
              <label key={priority} className="chip">
                <input
                  type="checkbox"
                  checked={selectedPriorities.includes(priority)}
                  onChange={() => togglePriority(priority)}
                />
                {priorityLabel(priority)}
              </label>
            ))}
          </fieldset>
        )
      case 'assignee':
        return (
          <label key="assignee" className="filter-select">
            <span>{t('filters.byAssignee')}</span>
            <select
              value={value.assignee_id ?? ''}
              onChange={(event) =>
                onChange({ ...value, assignee_id: event.target.value || undefined })
              }
            >
              <option value="">{t('tasks.anyone')}</option>
              {members.map((member) => (
                <option key={member.user_id} value={member.user_id}>
                  {member.first_name || member.username}
                </option>
              ))}
            </select>
          </label>
        )
      case 'project':
        return (
          <label key="project" className="filter-select">
            <span>{t('columns.column.project')}</span>
            <select
              value={value.project_id ?? ''}
              onChange={(event) =>
                onChange({ ...value, project_id: event.target.value || undefined })
              }
            >
              <option value="">{t('tasks.anyone')}</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>
        )
      case 'overdue':
        return (
          <label key="overdue" className="chip">
            <input
              type="checkbox"
              checked={value.overdue ?? false}
              onChange={(event) => onChange({ ...value, overdue: event.target.checked || undefined })}
            />
            {t('filters.overdue')}
          </label>
        )
      default:
        return null
    }
  }

  const unpinned = QUICK_FILTERS.map((entry) => entry.id).filter((id) => !pins.includes(id))

  return (
    <div className="filters">
      <form
        className="filters__search"
        role="search"
        onSubmit={(event) => {
          event.preventDefault()
          commitSearch()
        }}
      >
        <span className="visually-hidden">{t('app.search')}</span>
        <input
          type="search"
          value={term}
          placeholder={t('filters.searchPlaceholder')}
          onChange={(event) => setTerm(event.target.value)}
          onBlur={commitSearch}
        />
      </form>

      {/* Everything on this row is one filter, so it cannot wrap mid-group and
          push the rest of the bar onto the next line. */}
      <div className="filters__quick">
        {pins.map(renderPinned)}
      </div>

      <div className="filters__actions">
        {saved.length > 0 ? (
          <select
            className="filters__saved"
            aria-label={t('savedFilters.title')}
            value=""
            onChange={(event) => {
              const entry = saved.find((item) => item.name === event.target.value)
              if (entry) onChange({ ...(entry.filters as TaskFilters) })
            }}
          >
            <option value="">{t('savedFilters.title')}</option>
            {saved.map((entry) => (
              <option key={entry.name} value={entry.name}>
                {entry.name}
              </option>
            ))}
          </select>
        ) : null}

        {activeCount > 0 ? (
          <button
            type="button"
            className="link"
            onClick={() => setSavingAs((open) => !open)}
          >
            {t('savedFilters.save')}
          </button>
        ) : null}

        <button
          type="button"
          className="button button--ghost"
          aria-expanded={moreOpen}
          onClick={() => setMoreOpen((open) => !open)}
        >
          {t('filters.moreFilters')}
          {activeCount > 0 ? <span className="pill">{activeCount}</span> : null}
        </button>

        {activeCount > 0 ? (
          <button
            type="button"
            className="link"
            onClick={() => onChange({ sort: value.sort ?? 'created_at', direction: value.direction })}
          >
            {t('filters.clearAll')}
          </button>
        ) : null}
      </div>

      {savingAs ? (
        <form
          className="filters__save"
          onSubmit={(event) => {
            event.preventDefault()
            const name = savedName.trim()
            if (!name) return
            if (saved.some((entry) => entry.name === name) && !window.confirm(t('savedFilters.overwrite'))) {
              return
            }
            // Paging is not part of what somebody means by "my view", so the
            // saved filter starts from the first page when it is applied.
            const { limit: _limit, offset: _offset, ...filters } = value
            const next = upsertSavedFilter(saved, {
              name,
              filters: filters as Record<string, unknown>,
            })
            setSaved(next)
            writeSavedFilters(next)
            setSavedName('')
            setSavingAs(false)
            setSaveError(null)
          }}
        >
          <label>
            <span>{t('savedFilters.name')}</span>
            <input
              autoFocus
              maxLength={60}
              value={savedName}
              onChange={(event) => setSavedName(event.target.value)}
            />
          </label>
          <button type="submit" className="button button--primary">
            {t('app.save')}
          </button>
          <button type="button" className="link" onClick={() => setSavingAs(false)}>
            {t('app.cancel')}
          </button>
          {saveError ? (
            <span className="field__error" role="alert">
              {saveError}
            </span>
          ) : null}
        </form>
      ) : null}

      {saved.length > 0 && moreOpen ? (
        <div className="filters__saved-list">
          <span className="muted">{t('savedFilters.title')}</span>
          {saved.map((entry) => (
            <span key={entry.name} className="chip">
              {entry.name}
              <button
                type="button"
                className="icon-button"
                aria-label={`${t('savedFilters.delete')}: ${entry.name}`}
                onClick={() => {
                  if (!window.confirm(t('savedFilters.deleteConfirm', { name: entry.name }))) return
                  const next = removeSavedFilter(saved, entry.name)
                  setSaved(next)
                  writeSavedFilters(next)
                }}
              >
                <Icon name="close" size={12} />
              </button>
            </span>
          ))}
        </div>
      ) : null}

      {moreOpen ? (
        <div className="filters__more">
          {/* The unpinned controls, so switching a filter from "more" to "quick"
              is a drag of attention rather than a hunt through two places. */}
          {unpinned.length > 0 ? <div className="filters__quick">{unpinned.map(renderPinned)}</div> : null}

          <label className="chip">
            <input
              type="checkbox"
              checked={value.unfiled ?? false}
              onChange={(event) => onChange({ ...value, unfiled: event.target.checked || undefined })}
            />
            {t('tasks.noProject')}
          </label>

          <label className="filter-select">
            <span>{t('filters.sortBy')}</span>
            <select
              value={value.sort ?? 'created_at'}
              onChange={(event) => onChange({ ...value, sort: event.target.value })}
            >
              {SORTABLE.map((option) => (
                <option key={option.id} value={option.id}>
                  {t(option.label)}
                </option>
              ))}
            </select>
          </label>

          <label className="filter-select">
            <span>{t('filters.direction')}</span>
            <select
              value={value.direction ?? 'desc'}
              onChange={(event) =>
                onChange({ ...value, direction: event.target.value === 'asc' ? 'asc' : 'desc' })
              }
            >
              <option value="desc">{t('filters.descending')}</option>
              <option value="asc">{t('filters.ascending')}</option>
            </select>
          </label>

          <div className="filters__pins">
            <span className="filters__pins-label">{t('filters.quickFilters')}</span>
            {QUICK_FILTERS.map((entry) => (
              <label key={entry.id} className="chip">
                <input
                  type="checkbox"
                  checked={pins.includes(entry.id)}
                  onChange={(event) => setPin(entry.id, event.target.checked)}
                />
                {t(entry.label)}
              </label>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}

/** Parse the filter part of a query string into the API's filter object. */
export function filtersFromSearch(search: string): TaskFilters {
  const params = new URLSearchParams(search)
  const statuses = params
    .getAll('status')
    .filter((item): item is TaskStatus => (TASK_STATUSES as readonly string[]).includes(item))
  const priorities = params
    .getAll('priority')
    .filter((item): item is TaskPriority => (TASK_PRIORITIES as readonly string[]).includes(item))
  const direction = params.get('direction')
  const flag = (key: string) => (params.get(key) === '1' ? true : undefined)

  return {
    search: params.get('search') ?? undefined,
    status: statuses.length ? statuses : undefined,
    priority: priorities.length ? priorities : undefined,
    project_id: params.get('project') ?? undefined,
    assignee_id: params.get('assignee') ?? undefined,
    unfiled: flag('unfiled'),
    overdue: flag('overdue'),
    sort: params.get('sort') ?? 'created_at',
    direction: direction === 'asc' ? 'asc' : 'desc',
  }
}

/** The inverse of `filtersFromSearch`, so the URL is the single source of truth. */
export function filtersToSearch(filters: TaskFilters): string {
  const params = new URLSearchParams()
  if (filters.search) params.set('search', filters.search)
  for (const status of filters.status ?? []) params.append('status', status)
  for (const priority of filters.priority ?? []) params.append('priority', priority)
  if (filters.project_id) params.set('project', filters.project_id)
  if (filters.assignee_id) params.set('assignee', filters.assignee_id)
  if (filters.unfiled) params.set('unfiled', '1')
  if (filters.overdue) params.set('overdue', '1')
  if (filters.sort && filters.sort !== 'created_at') params.set('sort', filters.sort)
  if (filters.direction === 'asc') params.set('direction', 'asc')
  const encoded = params.toString()
  return encoded ? `?${encoded}` : ''
}
