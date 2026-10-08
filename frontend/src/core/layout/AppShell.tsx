import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { Avatar } from '../users/Avatar'
import { displayName } from '../auth/types'
import { useAsync } from '../hooks/useAsync'
import { useI18n, LOCALES } from '../i18n'
import type { TranslationKey } from '../i18n'
import { useOrganization } from '../organizations/OrganizationContext'
import { projectsApi } from '../projects/api'
import type { Project } from '../projects/api'
import { Listbox } from '../ui/Listbox'
import { Icon } from './Icon'
import type { IconName } from './Icon'
import { NavRow } from './NavRow'
import { navigatorGroupsFor } from './navigator'
import { useRailBadges } from './railBadges'
import type { NavigatorSectionId } from './navigator'

/**
 * The application shell (section 29), laid out the way Huly lays it out.
 *
 * Two panels and a status bar, in that order:
 *
 * - a **rail** of section icons, 4.25rem wide, that never changes shape and never
 *   scrolls. It answers "which part of the product am I in" with one glance, which
 *   is the only question it is responsible for answering.
 * - a **navigator** that lists what is inside the current section - the projects,
 *   the people, the saved views. This is the part that grows, and it scrolls on
 *   its own.
 * - a **status bar** across the content area carrying the two things that are not
 *   navigation: the organization and the account.
 *
 * The rail and the navigator both span the full height. A navigation panel that
 * stopped at the bottom of the status bar would suggest its list ends there.
 *
 * The sections come from the route rather than from a second source of truth: a
 * section is whatever the URL prefix says it is, so a deep link cannot open the
 * shell on a section that disagrees with the page.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { status, user, signOut } = useAuth()
  const { t } = useI18n()
  const [navOpen, setNavOpen] = useState(false)
  const [navCollapsed, setNavCollapsed] = useState(() => {
    try {
      return localStorage.getItem('tasktracker.nav-collapsed') === '1'
    } catch {
      return false
    }
  })
  const location = useLocation()
  const burgerRef = useRef<HTMLButtonElement>(null)

  // Navigating away from a drawer that is now off-screen is a dead end.
  useEffect(() => setNavOpen(false), [location.pathname])

  // Escape closes the drawer and returns focus to the burger, so a keyboard user
  // who opened it can fold it up again without reaching for the mouse.
  useEffect(() => {
    if (!navOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setNavOpen(false)
        burgerRef.current?.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [navOpen])

  const signedIn = status === 'authenticated'

  // The navigator can be folded away on windows wide enough for it and the page
  // side by side; below that it is a drawer and the collapsed state does not
  // apply (its own media query keeps the class from touching the drawer). The
  // choice survives reloads, like the theme and the language do.
  const collapse = (collapsed: boolean) => {
    setNavCollapsed(collapsed)
    try {
      localStorage.setItem('tasktracker.nav-collapsed', collapsed ? '1' : '0')
    } catch {
      /* storage unavailable: the panel still toggles for this session */
    }
  }

  return (
    // Without the panels the grid must lose their columns too, or the bar and the
    // page get squeezed beside two empty ones.
    <div
      className={`shell${signedIn ? '' : ' shell--no-nav'}${navOpen ? ' shell--nav-open' : ''}${
        signedIn && navCollapsed ? ' shell--nav-collapsed' : ''
      }`}
    >
      {signedIn ? <Rail /> : null}
      {signedIn ? <Navigator onNavigate={() => setNavOpen(false)} /> : null}
      {signedIn ? <div className="shell__nav-scrim" onClick={() => setNavOpen(false)} /> : null}

      <div className="shell__body">
        <header className="shell__bar">
          {/* One button for one job, in the place the burger sits: on a narrow
              window it opens the navigator's drawer, on a wide one it folds or
              unfolds the navigator's column. Only one of the two is on screen at
              a time - which one is decided by the same breakpoint that decides
              drawer versus column. */}
          {signedIn ? (
            <>
              <button
                ref={burgerRef}
                type="button"
                className="shell__burger"
                aria-label={t('nav.openMenu')}
                aria-expanded={navOpen}
                onClick={() => setNavOpen((open) => !open)}
              >
                <Icon name="tasks" />
              </button>

              <button
                type="button"
                className="shell__toggle"
                aria-label={navCollapsed ? t('nav.expand') : t('nav.collapse')}
                aria-expanded={!navCollapsed}
                onClick={() => collapse(!navCollapsed)}
              >
                <Icon
                  name="chevron"
                  size={16}
                  className={
                    navCollapsed
                      ? 'shell__toggle-icon shell__toggle-icon--expand'
                      : 'shell__toggle-icon'
                  }
                />
              </button>
            </>
          ) : null}

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

interface Section {
  id: NavigatorSectionId
  /**
   * URL prefixes that select this section. The longest match wins, so
   * `/users/me` opens Settings while `/users` itself belongs to People.
   */
  prefixes: string[]
  path: string
  icon: IconName
  label: string
}

/** The rail's entries: four of them, the number Huly keeps. */
function useSections(): Section[] {
  const { t } = useI18n()

  return [
    {
      id: 'projects',
      prefixes: ['/projects'],
      path: '/projects',
      icon: 'projects',
      label: t('nav.projects'),
    },
    { id: 'tasks', prefixes: ['/tasks'], path: '/tasks', icon: 'tasks', label: t('nav.tasks') },
    {
      id: 'people',
      // Three routes, one section: the views of an organization are not parts
      // of the product, and each claiming a rail icon would undo the point of
      // shrinking the rail. The rail lands on the first row of the navigator.
      prefixes: ['/members', '/users', '/structure'],
      path: '/users',
      icon: 'members',
      label: t('nav.people'),
    },
    {
      id: 'settings',
      // `/users/me` is the account's own profile - the longest matching prefix
      // keeps it in Settings even though it lives under `/users`.
      prefixes: ['/settings', '/users/me', '/preferences'],
      path: '/settings',
      icon: 'settings',
      label: t('nav.settings'),
    },
  ]
}

/** Which section the current URL belongs to; the longest prefix wins. */
function useActiveSection(sections: Section[]): Section | null {
  const { pathname } = useLocation()
  let match: Section | null = null
  let matchLength = 0
  for (const section of sections) {
    for (const prefix of section.prefixes) {
      if (pathname.startsWith(prefix) && prefix.length > matchLength) {
        match = section
        matchLength = prefix.length
      }
    }
  }
  return match
}

/**
 * The icon rail.
 *
 * Labels are not repeated here: at 4.25rem wide they would only truncate, and the
 * navigator that opens next to it already names the section. Each button still
 * carries its label as a tooltip and as an accessible name, so nothing is lost.
 */
function Rail() {
  const { t } = useI18n()
  const sections = useSections()
  const active = useActiveSection(sections)
  const badges = useRailBadges()

  return (
    <nav className="shell__rail rail" aria-label={t('app.more')}>
      <Link to="/" className="rail__logo" aria-label={t('app.name')}>
        TT
      </Link>

      {sections.map((section) => {
        const badge = badges[section.id]
        const showBadge = badge !== undefined && badge > 0
        return (
          <Link
            key={section.id}
            to={section.path}
            title={section.label}
            aria-label={showBadge ? `${section.label}: ${badge}` : section.label}
            aria-current={active?.id === section.id ? 'page' : undefined}
            className="rail__item-wrap"
          >
            <span
              className={active?.id === section.id ? 'rail__item rail__item--active' : 'rail__item'}
            >
              <Icon name={section.icon} size={20} />
            </span>
            {showBadge ? (
              <span className="rail__badge" aria-hidden="true">
                {badge > 99 ? '99+' : badge}
              </span>
            ) : null}
          </Link>
        )
      })}

      <span className="rail__spacer" />
    </nav>
  )
}

/**
 * The navigator.
 *
 * It lists the contents of the current section rather than the sections
 * themselves, which is what separates it from the rail. Fetching those lists is
 * the panel's own business: pages are not told they have a navigator, so adding
 * one never means editing every screen.
 */
function Navigator({ onNavigate }: { onNavigate: () => void }) {
  const { t } = useI18n()
  const sections = useSections()
  const active = useActiveSection(sections)

  if (active === null) {
    return (
      <nav className="shell__nav nav">
        <NavigatorHeader title={t('nav.home')} />
        <ul className="nav__list">
          <li>
            <NavRow to="/projects" icon="projects" label={t('nav.projects')} onNavigate={onNavigate} />
          </li>
        </ul>
      </nav>
    )
  }

  if (active.id === 'projects') return <ProjectsNavigator onNavigate={onNavigate} />
  if (active.id === 'tasks') return <TasksNavigator onNavigate={onNavigate} />
  if (active.id === 'people') return <PeopleNavigator onNavigate={onNavigate} />
  return <SettingsNavigator section={active} onNavigate={onNavigate} />
}

function NavigatorHeader({ title }: { title: string }) {
  return <div className="nav__header">{title}</div>
}

/**
 * A collapsible submenu (stage 1.9).
 *
 * The header toggles rather than navigates: a header that sometimes does one
 * and sometimes the other is a header nobody trusts. The group opens itself
 * when the current URL belongs to it, so a deep link arrives with its submenu
 * already unfolded, and once somebody clicks the header their choice sticks
 * for the rest of the visit.
 */
function NavGroup({
  titleKey,
  icon,
  active,
  content,
}: {
  titleKey: TranslationKey
  icon: IconName
  active: boolean
  /** The group's rows, as `<li>` elements; mounted only while open. */
  content: ReactNode
}) {
  const { t } = useI18n()
  const [override, setOverride] = useState<boolean | null>(null)
  const open = override ?? active

  return (
    <li className="nav__group">
      <button
        type="button"
        className={open ? 'nav__group-head nav__group-head--open' : 'nav__group-head'}
        aria-expanded={open}
        onClick={() => setOverride(!open)}
      >
        <Icon name={icon} size={15} />
        <span className="nav__label">{t(titleKey)}</span>
        <Icon name="chevron" size={13} className="nav__group-chevron" />
      </button>
      {open ? <ul className="nav__sublist">{content}</ul> : null}
    </li>
  )
}

/**
 * The submenus registered by the modules (stage 1.9).
 *
 * The shell cannot import them - `core` never depends on `modules` - so the
 * registry in `navigator.ts` is where a module declares what its section's
 * submenu holds, and this is where they render.
 */
function NavigatorGroups({
  section,
  onNavigate,
}: {
  section: NavigatorSectionId
  onNavigate: () => void
}) {
  const location = useLocation()
  const groups = navigatorGroupsFor(section)
  if (groups.length === 0) return null

  return (
    <>
      {groups.map((group) => (
        <NavGroup
          key={group.id}
          titleKey={group.titleKey}
          icon={group.icon}
          active={
            group.active
              ? group.active({ pathname: location.pathname, search: location.search })
              : false
          }
          content={group.content({ onNavigate })}
        />
      ))}
    </>
  )
}

function ProjectsNavigator({ onNavigate }: { onNavigate: () => void }) {
  const { t } = useI18n()
  const { current: organization } = useOrganization()
  const organizationId = organization?.id ?? null
  const projects = useAsync(
    () =>
      organizationId ? projectsApi.list(organizationId) : Promise.resolve<Project[]>([]),
    [organizationId],
  )

  return (
    <nav className="shell__nav nav">
      <NavigatorHeader title={t('nav.projects')} />

      <ul className="nav__list">
        <li>
          <NavRow to="/projects" icon="projects" label={t('projects.all')} end onNavigate={onNavigate} />
        </li>

        {(projects.data ?? []).map((project) => (
          <li key={project.id}>
            <NavRow
              to={`/projects/${project.id}`}
              icon="projects"
              label={project.name}
              onNavigate={onNavigate}
            />
          </li>
        ))}

        {projects.data && projects.data.length === 0 ? (
          <li>
            <p className="nav__empty">{t('projects.empty')}</p>
          </li>
        ) : null}
      </ul>
    </nav>
  )
}

function TasksNavigator({ onNavigate }: { onNavigate: () => void }) {
  const { t } = useI18n()

  return (
    <nav className="shell__nav nav">
      <NavigatorHeader title={t('nav.tasks')} />

      <ul className="nav__list">
        <li>
          {/* The two rows differ only by query string, and NavLink ignores it, so
              each one declares which parameter makes it the current view. Without
              `end` the first row also stays lit on a task's own page, where the
              list it points at is the section rather than the destination. */}
          <NavRow
            to="/tasks"
            icon="tasks"
            label={t('tasks.allTasks')}
            hides="unfiled"
            onNavigate={onNavigate}
          />
        </li>
        <li>
          {/* The inbox is the list of tasks filed under no project, which is the
              first question a new organization asks. */}
          <NavRow
            to="/tasks?unfiled=1"
            icon="filter"
            label={t('tasks.inbox')}
            requires={{ name: 'unfiled', value: '1' }}
            onNavigate={onNavigate}
          />
        </li>

        <NavigatorGroups section="tasks" onNavigate={onNavigate} />
      </ul>
    </nav>
  )
}

/**
 * The people section: two plain rows, the same for every visitor.
 *
 * What a row does once opened is the page's business and the server's: the
 * portal user list is a normal page now, and who may grant administrator
 * rights there is checked at the API, not hidden by which menu appeared.
 * Nothing in this panel collapses - the section is two destinations, and a
 * heading that merely expands to one of them would add a click for nothing.
 */
function PeopleNavigator({ onNavigate }: { onNavigate: () => void }) {
  const { t } = useI18n()

  return (
    <nav className="shell__nav nav">
      <NavigatorHeader title={t('nav.people')} />

      <ul className="nav__list">
        <li>
          <NavRow to="/users" icon="users" label={t('nav.users')} end onNavigate={onNavigate} />
        </li>
        <li>
          <NavRow to="/structure" icon="members" label={t('org.structure')} end onNavigate={onNavigate} />
        </li>

        <NavigatorGroups section="people" onNavigate={onNavigate} />
      </ul>
    </nav>
  )
}

function SettingsNavigator({
  section,
  onNavigate,
}: {
  section: Section
  onNavigate: () => void
}) {
  const { t } = useI18n()

  return (
    <nav className="shell__nav nav">
      <NavigatorHeader title={section.label} />

      <ul className="nav__list">
        <li>
          <NavRow to="/settings" icon="settings" label={t('nav.settings')} end onNavigate={onNavigate} />
        </li>
        <li>
          <NavRow to="/users/me" icon="user" label={t('nav.profile')} onNavigate={onNavigate} />
        </li>
        <li>
          <NavRow
            to="/preferences"
            icon="columns"
            label={t('preferences.title')}
            onNavigate={onNavigate}
          />
        </li>
      </ul>
    </nav>
  )
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
      <Listbox<string>
        value={current.id}
        options={organizations.map((organization) => ({
          value: organization.id,
          label: organization.name,
        }))}
        onChange={(next) => {
          if (!next) return
          // A different tenant means different projects and tasks, so the page
          // being looked at almost certainly does not exist over there.
          select(next)
          navigate('/projects')
        }}
      />
    </label>
  )
}

function LanguageSwitcher() {
  const { t, locale, setLocale } = useI18n()
  return (
    <div className="lang" role="group" aria-label={t('app.language')}>
      {LOCALES.map((entry) => (
        <button
          key={entry.id}
          type="button"
          className={locale === entry.id ? 'lang__item lang__item--active' : 'lang__item'}
          aria-pressed={locale === entry.id}
          title={entry.label}
          onClick={() => setLocale(entry.id)}
        >
          {entry.id.toUpperCase()}
        </button>
      ))}
    </div>
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
<Avatar src={user.avatar_url} name={displayName(user)} size="sm" className="account__avatar" />
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
