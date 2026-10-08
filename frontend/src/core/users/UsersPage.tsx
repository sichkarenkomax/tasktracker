import { useEffect, useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import { useAsync, useMutation } from '../hooks/useAsync'
import { useI18n } from '../i18n'
import { formatDateTime } from '../format'
import { usersApi } from './api'
import type { PortalUser } from './api'

/**
 * Every account registered on this installation.
 *
 * A different screen from an organization's members, not a wider version of it:
 * this one crosses tenants, so browsing it is open to everybody who can sign in.
 * Granting administrator rights is the exception - it is the only action in the
 * product that is not scoped to one organization, so it stays superuser-only,
 * and the server refuses it for anybody else exactly as it always did.
 */
export function UsersPage() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [term, setTerm] = useState('')
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)

  // Committed on submit or after a pause, so typing does not fire a request per
  // keystroke against the one endpoint that crosses every tenant.
  useEffect(() => {
    const handle = setTimeout(() => {
      setSearch(term.trim())
      setOffset(0)
    }, 300)
    return () => clearTimeout(handle)
  }, [term])

  const page = useAsync(() => usersApi.list({ search, limit: 50, offset }), [search, offset])

  const canAdmin = !!user?.is_superuser

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>{t('users.title')}</h1>
          <p className="muted">{t('users.subtitle')}</p>
        </div>
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
              placeholder={t('users.searchPlaceholder')}
              onChange={(event) => setTerm(event.target.value)}
            />
          </label>
        </form>
      </header>

      {page.error ? (
        <p className="notice notice--error" role="alert">
          {page.error}
        </p>
      ) : null}
      {page.loading && !page.data ? <p className="notice">{t('app.loading')}</p> : null}
      {page.data && page.data.items.length === 0 ? (
        <p className="notice">{t('users.empty')}</p>
      ) : null}

      {page.data ? (
        <>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">{t('auth.username')}</th>
                  <th scope="col">{t('members.email')}</th>
                  <th scope="col">{t('users.admin')}</th>
                  <th scope="col">{t('app.createdAt')}</th>
                  <th scope="col" />
                </tr>
              </thead>
              <tbody>
                {page.data.items.map((account) => (
                  <UserRow
                    key={account.id}
                    account={account}
                    isMe={account.id === user?.id}
                    canAdmin={canAdmin}
                    onChanged={page.reload}
                  />
                ))}
              </tbody>
            </table>
          </div>

          <Pagination page={page.data} offset={offset} setOffset={setOffset} />
        </>
      ) : null}
    </section>
  )
}

function Pagination({
  page,
  offset,
  setOffset,
}: {
  page: { total: number; limit: number }
  offset: number
  setOffset: (next: number) => void
}) {
  const { t } = useI18n()
  if (page.total <= page.limit) return null

  return (
    <nav className="pagination" aria-label={t('users.title')}>
      <button
        type="button"
        className="button button--ghost"
        disabled={offset === 0}
        onClick={() => setOffset(Math.max(0, offset - page.limit))}
      >
        {t('pagination.previous')}
      </button>
      <span className="muted">
        {t('pagination.showing', {
          from: offset + 1,
          to: Math.min(offset + page.limit, page.total),
          total: page.total,
        })}
      </span>
      <button
        type="button"
        className="button button--ghost"
        disabled={offset + page.limit >= page.total}
        onClick={() => setOffset(offset + page.limit)}
      >
        {t('pagination.next')}
      </button>
    </nav>
  )
}

function UserRow({
  account,
  isMe,
  canAdmin,
  onChanged,
}: {
  account: PortalUser
  isMe: boolean
  canAdmin: boolean
  onChanged: () => void
}) {
  const { t } = useI18n()
  const [error, setError] = useState<string | null>(null)

  const grant = useMutation<boolean, void>(async (value) => {
    await usersApi.setSuperuser(account.id, value)
  })

  return (
    <tr>
      <td>
        <strong>
          {account.first_name || account.username}
          {isMe ? <span className="muted"> ({t('users.you')})</span> : null}
        </strong>
        <br />
        <span className="muted">{account.username}</span>
      </td>
      <td>{account.email}</td>
      <td>
        {account.is_superuser ? (
          <span className="badge badge--project-active">{t('users.admin')}</span>
        ) : (
          <span className="muted">{t('app.no')}</span>
        )}
      </td>
      <td className="muted">{formatDateTime(account.created_at)}</td>
      <td>
        {isMe ? (
          // The server refuses this anyway; offering it would be a button that
          // exists only to fail.
          <span className="muted" />
        ) : canAdmin ? (
          <button
            type="button"
            className="link"
            disabled={grant.pending}
            onClick={async () => {
              setError(null)
              const done = await grant.run(!account.is_superuser)
              if (done !== null) onChanged()
              else setError(grant.error)
            }}
          >
            {account.is_superuser ? t('users.removeAdmin') : t('users.makeAdmin')}
          </button>
        ) : null}
        {error ? (
          <span className="field__error" role="alert">
            {error}
          </span>
        ) : null}
      </td>
    </tr>
  )
}
