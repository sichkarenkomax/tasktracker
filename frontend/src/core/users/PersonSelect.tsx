import { useI18n } from '../i18n'
import type { Member } from '../organizations/api'
import { displayName } from '../organizations/chartLayout'
import { getPeopleInfo } from '../settings/peopleInfo'
import { Listbox } from '../ui/Listbox'

/**
 * The listbox for choosing a person (stage 2.5).
 *
 * Seven places offer a roster - the assignee, the filter bar, co-assignees,
 * watchers, a department's head, somebody's placement, deputies - and each of them
 * was assembling the same three fields by hand. One component means a person is
 * described the same way everywhere, and a change to how a person is described is
 * one edit rather than seven.
 *
 * A row is a face, a name, and the org position underneath in a muted, smaller
 * line. The position alone, not "department · position": the department is a
 * grouping the reader is already standing inside when they are picking from that
 * department's roster, while the position is the thing that tells two similar
 * names apart (user's decision, 2.5). Someone with no position gets no second
 * line rather than an empty one.
 *
 * `searchable` is on by default and off only where the roster cannot be long: a
 * picker over three people with a search box in it is a step in the way.
 */
export interface PersonSelectProps {
  members: ReadonlyArray<Member>
  value: string | null
  onChange: (next: string | null) => void
  /** Text while nothing is chosen; also the label of the "nobody" row. */
  placeholder?: string
  /** Offer the "nobody" row as a choice (native `<select>`'s blank option). */
  clearable?: boolean
  disabled?: boolean
  /** Defaults to true: with a long roster, typing beats scrolling. */
  searchable?: boolean
  id?: string
  'aria-label'?: string
}

export function PersonSelect({
  members,
  value,
  onChange,
  placeholder,
  clearable,
  disabled,
  searchable = true,
  id,
  'aria-label': ariaLabel,
}: PersonSelectProps) {
  // Read once per render rather than threaded through: the choice is a personal
  // preference of the reader, like the date format, and every call site would
  // otherwise have to fetch and pass it down.
  const full = getPeopleInfo() === 'full'
  const { t } = useI18n()

  return (
    <Listbox<string>
      id={id}
      value={value}
      placeholder={placeholder}
      clearable={clearable}
      disabled={disabled}
      aria-label={ariaLabel}
      searchable={searchable}
      searchPlaceholder={t('listbox.searchPlaceholder')}
      nothingFoundLabel={t('listbox.nothingFound')}
      options={members.map((member) => ({
        value: member.user_id,
        label: displayName(member),
        secondary: full ? (member.position_title ?? undefined) : undefined,
        avatarUrl: member.avatar_url,
        // The search matches what is written on the row, and a name typed in
        // Latin is how half the roster is searched for.
        hint: full ? (member.position_title ?? undefined) : (member.username ?? undefined),
      }))}
      onChange={onChange}
    />
  )
}