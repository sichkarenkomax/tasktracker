import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { displayName } from '../auth/types'
import { useOrganization } from '../organizations/OrganizationContext'

/**
 * The shell every page renders inside (section 29: platform -> user -> projects ->
 * project -> tasks).
 *
 * The organization switcher lives here rather than on a page because almost every
 * screen depends on which tenant is active; making people go somewhere to change
 * it would put a step between a thought and the work.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { status, user, signOut } = useAuth()
  const { organizations, current, select, loading } = useOrganization()
  const navigate = useNavigate()
  const [switcherOpen, setSwitcherOpen] = useState(false)

  return (
    <div className="app-shell">
      <header className="app-shell__header">
        <Link to="/" className="app-shell__brand">
          TaskTracker
        </Link>

        {status === 'authenticated' ? (
          <nav className="app-shell__nav" aria-label="Main">
            <NavLink to="/projects">Projects</NavLink>
            <NavLink to="/tasks">All tasks</NavLink>
            <NavLink to="/settings">Settings</NavLink>
          </nav>
        ) : null}

        <div className="app-shell__account">
          {current && organizations.length > 0 ? (
            <details
              className="switcher"
              open={switcherOpen}
              onToggle={(event) => setSwitcherOpen(event.currentTarget.open)}
            >
              <summary>{loading ? 'Loading...' : current.name}</summary>
              <ul>
                {organizations.map((organization) => (
                  <li key={organization.id}>
                    <button
                      type="button"
                      className={
                        organization.id === current.id ? 'switcher__item switcher__item--active' : 'switcher__item'
                      }
                      onClick={() => {
                        select(organization.id)
                        setSwitcherOpen(false)
                      }}
                    >
                      {organization.name}
                    </button>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}

          {user ? (
            <span className="app-shell__user" title={user.email}>
              {displayName(user)}
            </span>
          ) : null}

          {status === 'authenticated' ? (
            <button
              type="button"
              className="link"
              onClick={async () => {
                await signOut()
                navigate('/login')
              }}
            >
              Sign out
            </button>
          ) : (
            <Link to="/login">Sign in</Link>
          )}
        </div>
      </header>

      <main className="app-shell__main">{children}</main>

      <footer className="app-shell__footer">
        <span className="muted">Self-hosted TaskTracker</span>
        <Link to="/system">Platform</Link>
      </footer>
    </div>
  )
}
