/**
 * Inline SVG icons.
 *
 * Drawn here rather than pulled from an icon package: the set is small, fixed,
 * and needs to inherit `currentColor` so it works in both themes without a second
 * asset. A package would add a dependency and a build step to avoid writing
 * twenty paths.
 *
 * The whole set is stroked, not filled. A filled path that was drawn as an outline
 * - the column icon especially - renders as a solid block that reads as a
 * checkbox, which is worse than no icon at all. One style, everywhere.
 *
 * All of them are `aria-hidden`: the accessible name comes from the adjacent text,
 * and an icon that repeats its label is noise to a screen reader.
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
  | 'edit'
  | 'save'
  | 'calendar'
  | 'trash'
  | 'eye'

const PATHS: Record<IconName, string> = {
  projects:
    'M3.5 7a2 2 0 0 1 2-2h3.4a2 2 0 0 1 1.6.8l1 1.2h7a2 2 0 0 1 2 2v7.8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2Z',
  tasks: 'M4 6.5h2.2M4 12h2.2M4 17.5h2.2M9.2 6.5H20M9.2 12H20M9.2 17.5H20',
  members:
    'M15.5 19.5v-1.2a3.3 3.3 0 0 0-3.3-3.3H7.3A3.3 3.3 0 0 0 4 18.3v1.2M9.8 11.8a3.3 3.3 0 1 0 0-6.6 3.3 3.3 0 0 0 0 6.6ZM16.4 8.6a2.6 2.6 0 0 1 0 5M20 19.5v-1.1a3 3 0 0 0-2-2.8',
  users:
    'M9.5 11.5a3.6 3.6 0 1 0 0-7.2 3.6 3.6 0 0 0 0 7.2ZM2.8 20v-1a4.5 4.5 0 0 1 4.5-4.5h4.4a4.5 4.5 0 0 1 4.5 4.5v1M16.8 5.2a3.4 3.4 0 0 1 0 6.6M18 14.8a4.5 4.5 0 0 1 3.4 4.4v.8',
  settings: 'M4 7h9.5M18.5 7H20M4 17h1.5M10.5 17H20M16 4.5v5M8 14.5v5',
  language:
    'M12 3.2a8.8 8.8 0 1 0 0 17.6 8.8 8.8 0 0 0 0-17.6ZM3.4 9.6h17.2M3.4 14.4h17.2M12 3.2c-4.3 4.8-4.3 12.8 0 17.6M12 3.2c4.3 4.8 4.3 12.8 0 17.6',
  plus: 'M12 5.2v13.6M5.2 12h13.6',
  search: 'M11 18.2a7.2 7.2 0 1 0 0-14.4 7.2 7.2 0 0 0 0 14.4ZM20.4 20.4l-4.2-4.2',
  filter: 'M4 6.5h16M7 12h10M10 17.5h4',
  columns: 'M4 5h16v14H4ZM9.6 5v14M14.8 5v14',
  user:
    'M12 11.4a3.6 3.6 0 1 0 0-7.2 3.6 3.6 0 0 0 0 7.2ZM4.6 20v-1a4.5 4.5 0 0 1 4.5-4.5h5.8a4.5 4.5 0 0 1 4.5 4.5v1',
  logout: 'M15 4.2h3a2 2 0 0 1 2 2v11.6a2 2 0 0 1-2 2h-3M10 8.2l-4 3.8 4 3.8M6.2 12h8.6',
  chevron: 'M8 10l4 4 4-4',
  grip: 'M9.5 6.5h.01M14.5 6.5h.01M9.5 12h.01M14.5 12h.01M9.5 17.5h.01M14.5 17.5h.01',
  check: 'M5.2 12.4l4.6 4.6L18.8 7.6',
  close: 'M6.4 6.4l11.2 11.2M17.6 6.4L6.4 17.6',
  edit: 'M4.5 19.5h4L19 9a2.1 2.1 0 0 0-3-3L5.5 16.5ZM15 6.5l2.5 2.5',
  save: 'M5 4.5h11L19.5 8v11.5a.5.5 0 0 1-.5.5H5a.5.5 0 0 1-.5-.5V5a.5.5 0 0 1 .5-.5ZM8 4.5v5h7v-5M8 20v-5.5h8V20',
  calendar:
    'M4.5 6.5h15v13h-15ZM4.5 10.5h15M8.5 4v4M15.5 4v4M9 14h2M13 14h2M9 17h2',
  trash: 'M4.5 6.5h15M9.5 6.5V4.8h5v1.7M6.5 6.5l1 13h9l1-13M10.2 10v6M13.8 10v6',
  eye: 'M2.6 12S6.4 5.8 12 5.8 21.4 12 21.4 12 17.6 18.2 12 18.2 2.6 12 2.6 12ZM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
}

export interface IconProps {
  name: IconName
  size?: number
  className?: string
}

export function Icon({ name, size = 18, className }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={PATHS[name]} />
    </svg>
  )
}
