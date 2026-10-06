/**
 * Inline SVG icons.
 *
 * Drawn here rather than pulled from an icon package: the set is small, fixed,
 * and needs to inherit `currentColor` so it works in both themes without a second
 * asset. A package would add a dependency and a build step to avoid writing
 * fifteen paths.
 *
 * All of them are `aria-hidden` - the accessible name always comes from the
 * adjacent text, and an icon that repeats its label is noise to a screen reader.
 */
export type IconName =
  | 'projects'
  | 'tasks'
  | 'members'
  | 'users'
  | 'settings'
  | 'language'
  | 'plus'
  | 'search'
  | 'filter'
  | 'columns'
  | 'user'
  | 'logout'
  | 'chevron'
  | 'grip'
  | 'check'
  | 'close'

const PATHS: Record<IconName, string> = {
  projects:
    'M3 7a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.6.8l.9 1.2H19a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z',
  tasks: 'M4 6h10M4 12h10M4 18h7M17 5.5l1.6 1.6L22 3.7M17 11.5l1.6 1.6L22 9.7',
  members:
    'M16 19v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 17.5V19M10 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM17 8.5a2.5 2.5 0 1 1 3 2.5M20 19v-1.2a3 3 0 0 0-2-2.8',
  users: 'M12 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM5 20v-1a4 4 0 0 1 4-4h6a4 4 0 0 1 4 4v1M18.5 14.5l.8 1.6 1.7.5-1.2 1.3.2 1.8-1.5-.8-1.6.8.3-1.8-1.2-1.3 1.7-.5Z',
  settings:
    'M4 7h9M17 7h3M4 17h3M11 17h9M15 4.5v5M8 14.5v5',
  language:
    'M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18M5.6 7.5h12.8M5.6 16.5h12.8',
  plus: 'M12 5v14M5 12h14',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM20 20l-4-4',
  filter: 'M4 6h16M7 12h10M10 18h4',
  columns: 'M4 5h16v14H4ZM9 5v14M15 5v14',
  user: 'M12 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM5 20v-1a4 4 0 0 1 4-4h6a4 4 0 0 1 4 4v1',
  logout: 'M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 8l-4 4 4 4M6 12h9',
  chevron: 'M8 10l4 4 4-4',
  grip: 'M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01',
  check: 'M5 12.5l4.5 4.5L19 7',
  close: 'M6 6l12 12M18 6L6 18',
}

/** Icons drawn as strokes rather than fills need this much padding around them. */
const STROKED: ReadonlySet<IconName> = new Set<IconName>([
  'tasks',
  'settings',
  'language',
  'plus',
  'search',
  'filter',
  'logout',
  'chevron',
  'check',
  'close',
])

export interface IconProps {
  name: IconName
  size?: number
  className?: string
}

export function Icon({ name, size = 18, className }: IconProps) {
  const stroked = STROKED.has(name)
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={stroked ? 'none' : 'currentColor'}
      stroke={stroked ? 'currentColor' : 'none'}
      strokeWidth={stroked ? 1.8 : 0}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={PATHS[name]} />
    </svg>
  )
}
