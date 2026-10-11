import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { formatDateTime } from '../format'
import { useAsync, useMutation } from '../hooks/useAsync'
import { useI18n } from '../i18n'
import { Icon } from '../layout/Icon'
import { organizationsApi } from '../organizations/api'
import type { OrganizationRole } from '../organizations/api'
import { useOrganization } from '../organizations/OrganizationContext'
import { RequiresOrganization } from '../organizations/RequiresOrganization'
import { ColumnSettingsPanel } from '../ui/ColumnSettingsPanel'
import { readColumns, writeColumns } from '../ui/columns'
import type { ColumnSet } from '../ui/columns'
import { Listbox } from '../ui/Listbox'
import { Avatar } from './Avatar'
import { usersApi } from './api'
import type { Person, PersonPage, PeopleQuery } from './api'
import { PresenceDot, PresenceLabel } from './presence'
import type { TranslationKey } from '../i18n'

/**
 * One list of people (stage 2.17).
 *
 * This replaces two screens: the organization's members and the directory of
 * every account on the installation. They answered different questions, but a
 * person looking for a colleague had to guess which screen they were on, and
 * the two disagreed about the same human - the directory knew nothing about a
 * role, the roster nothing about an account that was never invited. One table
 * with a column that says which kind of row this is answers both questions at
 * once, and the server decides what a person may see in it (stage 2.6).
 *
 * Everything that could be done in the table itself is deliberately not here:
 * no inline editing, no role dropdowns, no remove buttons. A row is a name to
 * click; what may be changed is behind that name, in the profile, where there
 * is room to ask for permission and show the result. Nine controls in a row of
 * fifty is how a list stops being readable.
 */
const COLUMN_IDS = [
  'name',
  'email',
  'department',
  'position',
  'role',
'status',
  'last_login_at',
  'last_seen',
] as const

type ColumnId = (typeof COLUMN_IDS)[number]

/** The name column is the row: without it there is nothing to click. */
const REQUIRED_COLUMNS: ReadonlySet<ColumnId> = new Set<ColumnId>(['name'])

const DEFAULT_COLUMNS: ColumnId[] = ['name', 'email', 'role', 'department', 'position', 'status']

const STORAGE_KEY = 'tasktracker.peopleColumns'

const ROLE_ORDER: OrganizationRole[] = ['owner', 'admin', 'member', 'viewer']

const SCOPES = ['members', 'all'] as const
type Scope = (typeof SCOPES)[number]

/** Sentinel for "no filter", kept out of the union so a null is never stored. */
const ANY = 'any'

export function PeoplePage() {
  return (
    <RequiresOrganization>
      <People />
    </RequiresOrganization>
  )
}

function People() {
  const { t } = useI18n()
  const { user } = useAuth()
  const { current: organization } = useOrganization()
  const organizationId = organization?.id ?? null

  const set = useMemo<ColumnSet<ColumnId>>(
    () => ({
      ids: COLUMN_IDS,
      labels: {
        name: t('people.column.name'),
        email: t('people.column.email'),
        department: t('people.column.department'),
        position: t('people.column.position'),
        role: t('people.column.role'),
        status: t('people.column.status'),
last_login_at: t('people.column.lastLogin'),
        // Presence is its own column rather than a rename of the login one (2.9):
        // they disagree, and the roster is read to answer "who is around", which
        // only the newer timestamp answers.
        last_seen: t('people.column.lastSeen'),
      },
      required: REQUIRED_COLUMNS,
      defaults: DEFAULT_COLUMNS,
      storageKey: STORAGE_KEY,
    }),
    [t],
  )

  const [columns, setColumns] = useState<ColumnId[]>(() => readColumns(set))
  const [configuring, setConfiguring] = useState(false)
  // The chooser floats above the table, anchored to this button, and hands the
  // focus back to it when it closes.
  const columnsButton = useRef<HTMLButtonElement>(null)
  const [term, setTerm] = useState('')
  const [search, setSearch] = useState('')
  const [scope, setScope] = useState<Scope>('members')
  const [role, setRole] = useState<OrganizationRole | null>(null)
  const [department, setDepartment] = useState<string | null>(null)
  const [position, setPosition] = useState<string | null>(null)
  const [sort, setSort] = useState<NonNullable<PeopleQuery['sort']>>('name')
  const [direction, setDirection] = useState<'asc' | 'desc'>('asc')
  const [offset, setOffset] = useState(0)
  const [adding, setAdding] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)

  // Debounced, like every list in the product: a request per keystroke against
  // the one endpoint that can cross the tenant boundary is a request per
  // keystroke across every account.
  useEffect(() => {
    const handle = setTimeout(() => {
      setSearch(term.trim())
      setOffset(0)
    }, 300)
    return () => clearTimeout(handle)
  }, [term])

  // Any change of what is being looked for starts again at the first page, or
  // page three of the old order is shown under a new filter.
  useEffect(() => {
    setOffset(0)
  }, [scope, role, department, position, sort, direction])

  const page = useAsync(() => {
    if (!organizationId) return Promise.resolve(null)
    return usersApi.people(organizationId, {
      search,
      scope,
      role: role ?? undefined,
      department_id: department ?? undefined,
      position_id: position ?? undefined,
      sort,
      direction,
      limit: 50,
      offset,
    })
  }, [organizationId, search, scope, role, department, position, sort, direction, offset])

  const structure = useAsync(
    () => (organizationId ? organizationsApi.structure(organizationId) : Promise.resolve(null)),
    [organizationId],
  )

  if (!organizationId) return null

  function applyColumns(next: ColumnId[]) {
    setColumns(next)
    writeColumns(set, next)
  }

  function sortBy(column: NonNullable<PeopleQuery['sort']>) {
    // Clicking the column the table is already ordered by reverses it, which is
    // the one thing a header click has to do without a second control.
    if (sort === column) {
      setDirection(direction === 'asc' ? 'desc' : 'asc')
    } else {
      setSort(column)
      setDirection('asc')
    }
  }

  const rows = page.data?.items ?? []
  const mayInvite = organization !== null

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>{t('people.title')}</h1>
          <p className="muted">{t('people.subtitle')}</p>
        </div>
        {mayInvite ? (
          <button
            type="button"
            className="button button--primary"
            onClick={() => setAdding((open) => !open)}
          >
            <Icon name="plus" size={15} />
            {t('members.add')}
          </button>
        ) : null}
      </header>

      {adding ? (
        <AddMember
          organizationId={organizationId}
          onDone={() => {
            setAdding(false)
            page.reload()
          }}
        />
      ) : null}

      <div className="table-toolbar">
        <form
          className="inline-form"
          role="search"
          onSubmit={(event) => {
            event.preventDefault()
            setSearch(term.trim())
            setOffset(0)
          }}
        >
          <label>
            <span className="visually-hidden">{t('app.search')}</span>
            <input
              type="search"
              value={term}
              placeholder={t('people.searchPlaceholder')}
              onChange={(event) => setTerm(event.target.value)}
            />
          </label>
        </form>

        <button
          type="button"
          className="button"
          aria-expanded={filtersOpen}
          onClick={() => setFiltersOpen((open) => !open)}
        >
          <Icon name="filter" size={15} />
          {t('filters.title')}
        </button>

<button
          type="button"
          className="button"
          ref={columnsButton}
          aria-expanded={configuring}
          aria-haspopup="dialog"
          onClick={() => setConfiguring((open) => !open)}
        >
          <Icon name="columns" size={15} />
          {t('columns.configure')}
        </button>
      </div>

      {filtersOpen ? (
        <div className="panel people-filters">
          <label className="field">
            <span>{t('people.scope')}</span>
            <Listbox<Scope>
              value={scope}
              options={[
                { value: 'members', label: t('people.scopeMembers') },
                // Accounts that exist here but belong to nobody are a portal
                // question, so the row is offered only to somebody who may
                // answer it; the server refuses anybody else the same way, and
                // offering it to them would be a filter that always errors.
                ...(user?.is_superuser
                  ? [{ value: 'all' as Scope, label: t('people.scopeAll') }]
                  : []),
              ]}
              onChange={(next) => {
                if (next !== null) setScope(next)
              }}
            />
          </label>

          <label className="field">
            <span>{t('people.column.role')}</span>
            <Listbox<string>
              value={role ?? ANY}
              options={[
                { value: ANY, label: t('people.any') },
                ...ROLE_ORDER.map((item) => ({
                  value: item,
                  label: t(`role.${item}` as TranslationKey),
                })),
              ]}
              onChange={(next) => {
                if (next !== null) setRole(next === ANY ? null : (next as OrganizationRole))
              }}
            />
          </label>

          <label className="field">
            <span>{t('people.column.department')}</span>
            <Listbox<string>
              value={department ?? ANY}
              options={[
                { value: ANY, label: t('people.any') },
                ...(structure.data?.departments ?? []).map((item) => ({
                  value: item.id,
                  label: item.name,
                })),
              ]}
              disabled={!structure.data}
              onChange={(next) => {
                if (next !== null) setDepartment(next === ANY ? null : next)
              }}
            />
          </label>

          <label className="field">
            <span>{t('people.column.position')}</span>
            <Listbox<string>
              value={position ?? ANY}
              options={[
                { value: ANY, label: t('people.any') },
                ...(structure.data?.positions ?? []).map((item) => ({
                  value: item.id,
                  label: item.title,
                })),
              ]}
              disabled={!structure.data}
              onChange={(next) => {
                if (next !== null) setPosition(next === ANY ? null : next)
              }}
            />
          </label>
        </div>
      ) : null}

{configuring ? (
          <ColumnSettingsPanel
            set={set}
            columns={columns}
            onChange={applyColumns}
            anchorRef={columnsButton}
            onClose={() => setConfiguring(false)}
          />
        ) : null}

      {page.error ? (
        <p className="notice notice--error" role="alert">
          {page.error}
        </p>
      ) : null}
      {page.loading && !page.data ? <p className="notice">{t('app.loading')}</p> : null}
      {page.data && rows.length === 0 ? (
        <p className="notice">{t('people.empty')}</p>
      ) : null}

      {page.data && rows.length > 0 ? (
        <>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  {columns.map((column) => (
                    <th key={column} scope="col">
                      <SortButton
                        label={set.labels[column]}
                        column={column}
                        sort={sort}
                        direction={direction}
                        onSort={sortBy}
                      />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((person) => (
                  <PersonRow key={person.id} person={person} columns={columns} />
                ))}
              </tbody>
            </table>
          </div>

          <Pagination page={page.data} offset={offset} onChange={setOffset} />
        </>
      ) : null}
    </section>
  )
}

/**
 * A sortable column header.
 *
 * The sort is the server's, so the header is a button that names the key it
 * asks for rather than a class that reorders rows in place: the arrow shows
 * which column and which way, and `aria-sort` says the same thing to a screen
 * reader instead of leaving it to guess from the arrow.
 */
function SortButton({
  label,
  column,
  sort,
  direction,
  onSort,
}: {
  label: string
  column: string
  sort: string
  direction: 'asc' | 'desc'
  onSort: (column: NonNullable<PeopleQuery['sort']>) => void
}) {
  const { t } = useI18n()
  const active = sort === column
  return (
    <button
      type="button"
      className="table__sort"
      aria-sort={active ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'}
      title={t('people.sortBy', { name: label })}
      onClick={() => onSort(column as NonNullable<PeopleQuery['sort']>)}
    >
      {label}
      {active ? (
        <span aria-hidden="true" className="table__sort-arrow">
          {direction === 'asc' ? '↑' : '↓'}
        </span>
      ) : null}
    </button>
  )
}

function PersonRow({ person, columns }: { person: Person; columns: ColumnId[] }) {
  const { t } = useI18n()
  const name = person.first_name || person.username

  /** One cell per column, so hiding a column hides its cell too. */
  function cell(column: ColumnId): React.ReactNode {
    switch (column) {
case 'name':
        return (
          <Link to={`/users/${person.id}`} className="people__name">
            {/* The dot sits on the picture rather than beside the name: the name
                is what the eye follows down the column, and a mark attached to
                it would read as part of the name (2.9). */}
            <span className="people__avatar">
              <Avatar src={person.avatar_url} name={name} size="sm" />
              <PresenceDot
                lastSeen={person.last_seen}
                visible={person.last_seen_visible}
              />
            </span>
            <span>
              <strong>{name}</strong>
              {person.first_name ? <span className="muted"> @{person.username}</span> : null}
            </span>
          </Link>
        )
      case 'email':
        return person.contacts_visible ? (
          person.email ?? <span className="muted">—</span>
        ) : (
          // Not a dash: a colleague who kept their contacts private is a fact
          // worth stating, and an empty cell next to somebody who simply has no
          // address on file is a different statement.
          <span className="muted" title={t('profile.contactsHidden')}>
            {t('people.hidden')}
          </span>
        )
      case 'department':
        return person.department_name ?? <span className="muted">—</span>
      case 'position':
        return person.position_title ?? <span className="muted">—</span>
      case 'role':
        return person.in_organization ? (
          <span className="badge">{t(`role.${person.role ?? 'member'}` as TranslationKey)}</span>
        ) : (
          <span className="badge badge--project-active">{t('people.outside')}</span>
        )
      case 'status':
        return person.status === 'active' ? (
          <span className="muted">—</span>
        ) : (
          <span className="badge badge--project-overdue">
            {t(`people.status.${person.status}` as TranslationKey)}
          </span>
        )
case 'last_login_at':
        return person.last_login_at ? (
          // Withheld with the presence the person hid (2.9): the sign-in time is
          // the same fact, written a week earlier. A dash would say "never".
          person.last_seen_visible ? (
            formatDateTime(person.last_login_at)
          ) : (
            <span className="muted">{t('people.hidden')}</span>
          )
        ) : (
          <span className="muted">{t('people.never')}</span>
        )
      case 'last_seen':
        return (
          <PresenceLabel lastSeen={person.last_seen} visible={person.last_seen_visible} />
        )
    }
  }

  return (
    <tr>
      {columns.map((column) => (
        <td key={column}>{cell(column)}</td>
      ))}
    </tr>
  )
}

function Pagination({
  page,
  offset,
  onChange,
}: {
  page: PersonPage
  offset: number
  onChange: (next: number) => void
}) {
  const { t } = useI18n()
  if (page.total <= page.limit) return null

  const from = offset + 1
  const to = Math.min(offset + page.limit, page.total)

  return (
    <nav className="pagination" aria-label={t('people.title')}>
      <button
        type="button"
        className="button button--ghost"
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - page.limit))}
      >
        {t('pagination.previous')}
      </button>
      <span className="muted">{t('pagination.showing', { from, to, total: page.total })}</span>
      <button
        type="button"
        className="button button--ghost"
        disabled={to >= page.total}
        onClick={() => onChange(offset + page.limit)}
      >
        {t('pagination.next')}
      </button>
    </nav>
  )
}

/**
 * Inviting somebody who is already on the installation.
 *
 * Moved here from the members screen rather than rewritten: the list of people
 * is where a person goes to add somebody, and a second "add" button on a page
 * that no longer exists would be a hole in the product.
 */
function AddMember({
  organizationId,
  onDone,
}: {
  organizationId: string
  onDone: () => void
}) {
  const { t } = useI18n()
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<OrganizationRole>('member')

  const add = useMutation<{ email: string; role: OrganizationRole }, void>(async (input) => {
    await organizationsApi.addMember(organizationId, input.email, input.role)
  })

  return (
    <form
      className="panel"
      onSubmit={async (event) => {
        event.preventDefault()
        const done = await add.run({ email: email.trim(), role })
        // Only close on success: a rejected invite must leave the typed address
        // in place so the person can fix a typo rather than retype it.
        if (done !== null) {
          setEmail('')
          onDone()
        }
      }}
    >
      <h2>{t('members.addTitle')}</h2>
      <p className="muted">{t('members.addHint')}</p>

      <div className="fields">
        <label className="field">
          <span>{t('members.email')}</span>
          <input
            autoFocus
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label className="field">
          <span>{t('members.role')}</span>
          <Listbox<OrganizationRole>
            value={role}
            options={(['admin', 'member', 'viewer'] as OrganizationRole[]).map((option) => ({
              value: option,
              label: t(`role.${option}` as TranslationKey),
            }))}
            onChange={(next) => {
              if (next !== null) setRole(next)
            }}
          />
        </label>
      </div>

      <div className="create-form__actions">
        <button type="submit" className="button button--primary" disabled={add.pending}>
          {add.pending ? t('app.loading') : t('members.add')}
        </button>
        <button type="button" className="button" onClick={onDone}>
          {t('app.cancel')}
        </button>
      </div>

      {add.error ? (
        <p className="notice notice--error" role="alert">
          {add.error}
        </p>
      ) : null}
    </form>
  )
}