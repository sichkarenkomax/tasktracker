import { useEffect, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { displayName } from '../auth/types'
import { useI18n, LOCALES } from '../i18n'
import { useOrganization } from '../organizations/OrganizationContext'
import { Icon } from './Icon'
import type { IconName } from './Icon'

/**
 * The application shell (section 29).
 *
 * The menu is a left sidebar because every authenticated screen belongs to one of
 * its four sections, and a horizontal bar hides them behind a burger on exactly
 * the laptop widths where a person is most likely to be scanning for the next
 * action. The bar keeps only the two things that are not navigation: the
 * organization switcher and the account menu.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { status, user, signOut } = useAuth()
  const { t } = useI18n()
  const [navOpen, setNavOpen] = useState(false)
  const location = useLocation()

  // Navigating away from a mobile menu that is now off-screen is a dead end.
  useEffect(() => setNavOpen(false), [location.pathname])

  const signedIn = status === 'authenticated'

  return (
    <div className={`shell${navOpen ? ' shell--nav-open' : ''}`}>
      {signedIn ? (
        <nav className="shell__nav" aria-label={t('app.more')}>
          <SidebarLink to="/projects" icon="projects" label={t('nav.projects')} />
          <SidebarLink to="/tasks" icon="tasks" label={t('nav.allTasks')} />
          <SidebarLink to="/members" icon="members" label={t('nav.members')} />
          <PortalAdminLink />
          <SidebarLink to="/settings" icon="settings" label={t('nav.settings')} />
        </nav>
      ) : null}

      <div className="shell__body">
        <header className="shell__bar">
          <button
            type="button"
            className="shell__burger"
            aria-label={t('nav.openMenu')}
            aria-expanded={navOpen}
            onClick={() => setNavOpen((open) => !open)}
          >
            <Icon name="tasks" />
          </button>

          <Link to="/" className="shell__brand">
            {t('app.name')}
          </Link>

          <div className="shell__bar-right">
            <OrganizationSwitcher />
            <LanguageSwitcher />
            {user ? <AccountMenu onSignOut={signOut} /> : <Link to="/login">{t('nav.signIn')}</Link>}
          </div>
        </header>

        <main className="shell__main">{children}</main>
      </div>
    </div>
  )
}

function SidebarLink({
  to,
  icon,
  label,
}: {
  to: string
  icon: IconName
  label: string
}) {
  return (
    <NavLink
      to={to}
      end={to === '/projects'}
      className={({ isActive }) => (isActive ? 'shell__link shell__link--active' : 'shell__link')}
    >
      <Icon name={icon} />
      <span>{label}</span>
    </NavLink>
  )
}

/**
 * The portal user list is only meaningful to somebody who can grant
 * administrator rights, so it appears for them and nobody else.
 */
function PortalAdminLink() {
  const { t } = useI18n()
  const { user } = useAuth()
  if (!user?.is_superuser) return null
  return <SidebarLink to="/users" icon="users" label={t('nav.users')} />
}

function OrganizationSwitcher() {
  const { t } = useI18n()
  const { organizations, current, select } = useOrganization()
  const navigate = useNavigate()

  if (!current) return null

  if (organizations.length === 1) {
    return <span className="shell__org">{current.name}</span>
  }

  return (
    <label className="shell__switcher">
      <span className="visually-hidden">{t('nav.organization')}</span>
      <select
        value={current.id}
        onChange={(event) => {
          // A different tenant means different projects and tasks, so the page
          // being looked at almost certainly does not exist over there.
          select(event.target.value)
          navigate('/projects')
        }}
      >
        {organizations.map((organization) => (
          <option key={organization.id} value={organization.id}>
            {organization.name}
          </option>
        ))}
      </select>
    </label>
  )
}

function LanguageSwitcher() {
  const { t, locale, setLocale } = useI18n()
  return (
    <label className="shell__switcher" title={t('app.language')}>
      <Icon name="language" />
      <span className="visually-hidden">{t('app.language')}</span>
      <select value={locale} onChange={(event) => setLocale(event.target.value as 'en' | 'ru')}>
        {LOCALES.map((entry) => (
          <option key={entry.id} value={entry.id}>
            {entry.label}
          </option>
        ))}
      </select>
    </label>
  )
}

/**
 * The account menu.
 *
 * Clicking the name opens the person's own settings, which is where they expect
 * to find their name, password and language - not under "portal settings", which
 * is somebody else's department.
 */
function AccountMenu({ onSignOut }: { onSignOut: () => Promise<void> }) {
  const { t } = useI18n()
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  if (!user) return null

  return (
    <div className="account">
      <button
        type="button"
        className="account__trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="account__avatar" aria-hidden="true">
          {displayName(user).charAt(0).toUpperCase()}
        </span>
        <span className="account__name">{displayName(user)}</span>
        <Icon name="chevron" size={14} />
      </button>

      {open ? (
        <>
          {/* Clicking away closes the menu; the overlay also stops the click from
              reaching the page underneath, which is what a menu actually is. */}
          <div className="account__scrim" onClick={() => setOpen(false)} />
          <div className="account__menu" role="menu">
            <Link
              to="/users/me"
              role="menuitem"
              className="account__item"
              onClick={() => setOpen(false)}
            >
              <Icon name="user" />
              {displayName(user)}
            </Link>
            <button
              type="button"
              role="menuitem"
              className="account__item"
              onClick={async () => {
                setOpen(false)
                await onSignOut()
                navigate('/login')
              }}
            >
              <Icon name="logout" />
              {t('nav.signOut')}
            </button>
          </div>
        </>
      ) : null}
    </div>
  )
}
