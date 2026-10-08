import { NavLink, useLocation, useSearchParams } from 'react-router-dom'

import { Icon } from './Icon'
import type { IconName } from './Icon'

/**
 * One navigation row (stage 1.9: moved out of the shell so a module-owned
 * submenu can offer the same row the built-in navigators use).
 *
 * React Router's NavLink compares pathnames and ignores the query string, so
 * two rows pointing at /tasks and /tasks?unfiled=1 both look active. Each row
 * therefore carries its own query-level activation rule (`requires`, `hides`
 * or `matches`), and that rule is combined with NavLink's pathname answer:
 * without the pathname half, a row with no query rule of its own would be lit
 * on every page of its section, including the ones where another row is the
 * actual destination.
 */
export function NavRow({
  to,
  icon,
  label,
  end,
  requires,
  hides,
  matches,
  onNavigate,
}: {
  to: string
  icon?: IconName
  label: string
  end?: boolean
  /** Active only while this query parameter holds this value. */
  requires?: { name: string; value: string }
  /** Inactive while this query parameter is present at all. */
  hides?: string
  /** Active only while the query string is an exact match for this one. */
  matches?: string
  onNavigate: () => void
}) {
  const [params] = useSearchParams()
  const { search } = useLocation()

  const ownActive =
    matches !== undefined
      ? canonicalSearch(search) === canonicalSearch(matches)
      : requires
        ? params.get(requires.name) === requires.value
        : hides === undefined || !params.has(hides)

  return (
    <NavLink
      to={to}
      end={end}
      onClick={onNavigate}
      className={({ isActive }) =>
        ownActive && isActive ? 'nav__item nav__item--active' : 'nav__item'
      }
    >
      {icon ? <Icon name={icon} size={15} /> : null}
      <span className="nav__label">{label}</span>
    </NavLink>
  )
}

/**
 * Query order carries no meaning, so rows compare query strings as sets of
 * parameters: a filter saved before a new parameter existed still equals the
 * URL that encodes it today.
 */
function canonicalSearch(search: string): string {
  return [...new URLSearchParams(search).entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${value}`)
    .join('&')
}
