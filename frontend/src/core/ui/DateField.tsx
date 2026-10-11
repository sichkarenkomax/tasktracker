import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { useI18n } from '../i18n'
import { Icon } from '../layout/Icon'

/**
 * A date field in place of the native `<input type="date">` (stage 1.5 follow-up).
 *
 * The native control cannot be themed: Chromium draws its calendar popup itself,
 * including the highlighted day, and that colour ignores `accent-color` - proven
 * on Chrome 154 by forcing a loud accent on the field and counting pixels in the
 * open popup (none of them came back). The same is true of the popup's own
 * chrome, its locale handling and its dark-mode colours. The rest of the stage-1
 * work already went this way for `<select>` (see Listbox), so the date picker is
 * the same trade: a component we can paint, in exchange for writing the keyboard
 * behaviour ourselves.
 *
 * The shape follows the APG date-picker dialog: a button that owns a portalled
 * `role="dialog"`, focus moved into the grid on open, arrows walking the days,
 * PageUp/PageDown walking the months, Escape handing focus back to the button.
 * Real focus (rather than `aria-activedescendant`) because the grid is two
 * dimensional, where a single active descendant stops being readable.
 *
 * Days are plain local `y/m/d` numbers and never `Date` objects: a date has no
 * zone, and letting the zone in is how a deadline set on the 8th comes back as
 * the 7th.
 */

export interface DateFieldProps {
  /**
   * `YYYY-MM-DD` when the field is date-only, or a full instant
   * (`2026-10-08T15:00:00Z`) when `withTime` is set. null/'' means "not set".
   */
  value: string | null
  onChange: (next: string | null) => void

  /**
   * Adds an hour and minute to the popup, and makes the value an instant.
   *
   * A deadline that can be 18:00 is an instant, and the API stores one (the
   * column grew from `date` to `timestamptz`), so the two modes cannot share a
   * value shape: with time, picking a day means "that day at the shown time".
   */
  withTime?: boolean

  /**
   * The time a day pick starts from when nothing is set yet. "end-of-day" suits a
   * deadline - choosing a day means "by the end of it" - and "now" suits a planned
   * start, which is being written down from this moment.
   */
  timeDefault?: 'end-of-day' | 'now'

  placeholder?: string
  disabled?: boolean
  /** Marks the control as holding a value the form will reject (native `required`). */
  invalid?: boolean
  /** Earliest / latest selectable day, `YYYY-MM-DD`. */
  min?: string | null
  max?: string | null

  /** Extra classes for the trigger - size and layout rules of the host page. */
  className?: string
  id?: string
  'aria-label'?: string
}

interface DateParts {
  y: number
  /** Zero-based, the way `Date.getMonth` counts. */
  m: number
  d: number
}

interface MenuPosition {
  top: number
  left: number
  maxHeight: number
}

const MENU_GAP = 6
const EDGE_GAP = 8
/** A grid is always six weeks tall, so the popup's height does not jump between
 *  months as the cursor moves from one to the next. */
const WEEKS = 6
const DAYS_IN_WEEK = 7
/** Months and years are both picked from a twelve-cell page: three rows of four,
 *  the shape a phone calendar uses. */
const PICK_PAGE = 12
const PICK_COLUMNS = 4

export function DateField(props: DateFieldProps) {
  const { locale, t } = useI18n()
  const withTime = props.withTime === true
  const [open, setOpen] = useState(false)
  const [view, setView] = useState<DateParts>(() => startOfMonth(selectedParts(props) ?? today()))
  const [cursor, setCursor] = useState<string>(() => isoOf(selectedParts(props) ?? today()))
  /** Which of the three grids the popup shows. Days are where picking starts;
   *  the month and the year in the title are how somebody gets to a far-off date
   *  without clicking an arrow a few hundred times. */
  const [panel, setPanel] = useState<'days' | 'months' | 'years'>('days')
  const [position, setPosition] = useState<MenuPosition | null>(null)
// The clock is held apart from the value so that typing "1" on the way to "18"
// does not store 01:00 and ask the server to save it. The ref mirrors it because
// `blur` can arrive in the same tick as the last keystroke, before React has
// re-rendered - reading the state there would save the previous hour.
  const [clock, setClock] = useState<Clock>(() => clockOf(props))
  const clockRef = useRef(clock)

  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const dayRefs = useRef(new Map<string, HTMLButtonElement>())
  const monthRefs = useRef(new Map<number, HTMLButtonElement>())
  const yearRefs = useRef(new Map<number, HTMLButtonElement>())
  const restoreFocusRef = useRef(false)
  const reactId = useId()

  const menuId = `datefield-${reactId}`
  const titleId = `${menuId}-title`
  const hoursId = `${menuId}-hours`
  const minutesId = `${menuId}-minutes`

  const selected = selectedParts(props)
  const placeholder = props.placeholder ?? t('date.placeholder')
  const openable = !props.disabled

  const months = useMemo(
    () => buildMonth(view.y, view.m, locale),
    [view.y, view.m, locale],
  )
  // The title is two buttons rather than one piece of text: the month and the
  // year are the two things a person reaches for when the date they want is not
  // in this month.
  const monthNames = useMemo(
    () =>
      Array.from({ length: 12 }, (_, index) =>
        new Intl.DateTimeFormat(locale, { month: 'short' }).format(new Date(2026, index, 1)).replace('.', ''),
      ),
    [locale],
  )
  const monthTitle = useMemo(
    () => new Intl.DateTimeFormat(locale, { month: 'long' }).format(new Date(view.y, view.m, 1)),
    [locale, view.y, view.m],
  )
  /** The twelve years on the page: the anchor year rounded down to a page edge. */
  const yearPageStart = Math.floor(view.y / PICK_PAGE) * PICK_PAGE
  const triggerText = selected
    ? withTime
      ? `${formatDate(selected, locale)}, ${pad2(clock.h)}:${pad2(clock.m)}`
      : formatDate(selected, locale)
    : placeholder

  function show() {
    const from = selected ?? today()
    setView(startOfMonth(from))
    setCursor(isoOf(from))
    setPanel('days')
    // Re-read the clock from the value: it may have been edited and saved while
    // the popup was shut.
    setClock(clockOf(props))
    setOpen(true)
  }

  function close(restoreFocus: boolean) {
    setOpen(false)
    // Not a direct focus() call: the focused day is about to be unmounted with
    // the menu, and a node removed while focused drops focus onto the document.
    // The hand-back happens after that commit, below.
    if (restoreFocus) restoreFocusRef.current = true
  }

  function pick(parts: DateParts) {
    props.onChange(withTime ? toInstant(parts, clockRef.current) : isoOf(parts))
    close(true)
  }

  /** The clock edits only become a value once the reader leaves the box. */
  function commitClock(next: Clock) {
    clockRef.current = next
    setClock(next)
    if (!selected) return
    props.onChange(toInstant(selected, next))
  }

  /** A day the caller may not choose: outside `min`/`max`. */
  function isBlocked(parts: DateParts): boolean {
    const iso = isoOf(parts)
    if (props.min && iso < props.min) return true
    if (props.max && iso > props.max) return true
    return false
  }

  function moveCursor(to: DateParts) {
    setCursor(isoOf(to))
    // Walking off the edge of the shown month brings that month along, so the
    // cursor never leaves a grid it is not drawn in.
    if (to.m !== view.m || to.y !== view.y) setView(startOfMonth(to))
  }

  function shiftMonth(delta: number) {
    const here = parseIso(cursor) ?? today()
    const from = startOfMonth(here)
    const next = new Date(from.y, from.m + delta, 1)
    // The day of the month is kept, clamped: 31 January plus one month is the
    // end of February, not 3 March.
    moveCursor({ y: next.getFullYear(), m: next.getMonth(), d: Math.min(here.d, daysInMonth(next.getFullYear(), next.getMonth())) })
  }

  /** The month page's arrows walk years, so the month underneath is kept. */
  function shiftYear(delta: number) {
    setView((current) => ({ ...current, y: current.y + delta }))
  }

  /** The year page's arrows walk whole pages of twelve, keeping the year in
   *  sight on the page it was on. */
  function shiftYearPage(delta: number) {
    setView((current) => {
      const start = Math.floor(current.y / PICK_PAGE) * PICK_PAGE
      return { ...current, y: start + delta * PICK_PAGE + (current.y - start) }
    })
  }

  /** Month chosen from the month page: back to the days, on that month. */
  function chooseMonth(month: number) {
    const here = parseIso(cursor) ?? today()
    moveCursor({ y: view.y, m: month, d: Math.min(here.d, daysInMonth(view.y, month)) })
    setPanel('days')
  }

  /** Year chosen from the year page: one step down to the months of that year. */
  function chooseYear(year: number) {
    setView((current) => ({ ...current, y: year }))
    setPanel('months')
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    // Each grid answers arrows and PageUp/PageDown for itself, and the clock
    // columns answer the same keys themselves, so a key coming from one of those
    // belongs to it - without these guards, arrow keys inside the hour box moved
    // the *date* while the hour sat still.
    const target = event.target as HTMLElement
    const onDay = target.classList?.contains('datefield__day') === true
    const onMonth = target.classList?.contains('datefield__month') === true
    const onYear = target.classList?.contains('datefield__year') === true

    if (event.key === 'Escape') {
      event.preventDefault()
      close(true)
      return
    }

    // Arrows walk a twelve-cell page by DOM focus, the way the clock columns do.
    // Enter and Space need nothing here: activating a button is the browser's
    // own job, so the click handler runs.
    if (onMonth || onYear) {
      if (stepFocus(event, PICK_COLUMNS)) return
      if (event.key === 'PageUp') {
        event.preventDefault()
        if (onMonth) shiftYear(-1)
        else shiftYearPage(-1)
      } else if (event.key === 'PageDown') {
        event.preventDefault()
        if (onMonth) shiftYear(1)
        else shiftYearPage(1)
      }
      return
    }

    if (!onDay) return

    const here = parseIso(cursor) ?? today()
    switch (event.key) {
      case 'ArrowLeft':
        event.preventDefault()
        moveCursor(addDays(here, -1))
        break
      case 'ArrowRight':
        event.preventDefault()
        moveCursor(addDays(here, 1))
        break
      case 'ArrowUp':
        event.preventDefault()
        moveCursor(addDays(here, -DAYS_IN_WEEK))
        break
      case 'ArrowDown':
        event.preventDefault()
        moveCursor(addDays(here, DAYS_IN_WEEK))
        break
      case 'PageUp':
        event.preventDefault()
        shiftMonth(event.shiftKey ? -12 : -1)
        break
      case 'PageDown':
        event.preventDefault()
        shiftMonth(event.shiftKey ? 12 : 1)
        break
      case 'Home':
        event.preventDefault()
        moveCursor(startOfWeek(here))
        break
      case 'End':
        event.preventDefault()
        moveCursor(endOfWeek(here))
        break
      case 'Enter':
      case ' ': {
        event.preventDefault()
        const picked = parseIso(cursor)
        if (picked && !isBlocked(picked)) pick(picked)
        break
      }
      case 'Tab':
        // Tabbing out of the popup folds it, but a Tab *inside* it - from the
        // hours to the minutes - must not: the reader is on their way to the
        // control they wanted, not out of the control they opened.
        setOpen(false)
        break
      default:
        break
    }
  }

  // Measuring happens once per opening, before paint, so the popup is never
  // painted in an unflipped position.
  useLayoutEffect(() => {
    if (!open) {
      setPosition(null)
      return
    }
    const menu = menuRef.current
    const trigger = triggerRef.current
    if (!menu || !trigger) return
    setPosition(computePosition(trigger.getBoundingClientRect(), menu.offsetHeight, menu.offsetWidth))
  }, [open])

  // The grid takes real focus on open, on the chosen day or on today.
  //
  // Not on the opening commit: the menu paints its first frame with
  // `visibility: hidden` (its position is only known after the measuring pass
  // above), and focus() on a hidden element is a silent no-op. Waiting for a
  // measured position is what makes the keyboard arrive inside the grid.
  useLayoutEffect(() => {
    if (!open || position === null) return
    if (panel === 'months') {
      monthRefs.current.get(view.m)?.focus()
      return
    }
    if (panel === 'years') {
      yearRefs.current.get(view.y)?.focus()
      return
    }
    dayRefs.current.get(cursor)?.focus()
  }, [open, position, panel, cursor, view.y, view.m])

  // Focus goes back to the trigger once the popup is gone, so a keyboard user who
// picked a day lands on the control they picked it in rather than at the top of
// the document.
//
// It cannot be done in the click handler: the focused day is unmounted with the
// menu, and a node removed while focused drops focus onto the document. Nor can
// it wait only for the closing commit - the page may disable the trigger for the
// moment it takes to save (a disabled button refuses focus), so the hand-back
// retries on the next commit until the button takes focus again.
useLayoutEffect(() => {
  if (!restoreFocusRef.current) return
  const trigger = triggerRef.current
  if (!trigger || trigger.disabled) return
  restoreFocusRef.current = false
  trigger.focus()
})

// Portalled and `fixed`, so the popup follows the field through the page's
  // scrolls and the window's resizes.
  useEffect(() => {
    if (!open) return
    const reposition = () => {
      const trigger = triggerRef.current
      const menu = menuRef.current
      if (!trigger || !menu) return
      setPosition(computePosition(trigger.getBoundingClientRect(), menu.offsetHeight, menu.offsetWidth))
    }
    window.addEventListener('scroll', reposition, true)
    window.addEventListener('resize', reposition)
    return () => {
      window.removeEventListener('scroll', reposition, true)
      window.removeEventListener('resize', reposition)
    }
  }, [open])

  // A value that changed underneath us (a reload, another edit) moves the grid
  // with it, rather than leaving it on the month it was opened with.
  useEffect(() => {
    if (open || !selected) return
    setView(startOfMonth(selected))
    setCursor(isoOf(selected))
    setPanel('days')
  }, [open, selected])

  // Clicking away closes. Pointer events rather than click, so the decision
  // lands before whatever was clicked takes focus.
  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node | null
      if (!target) return
      if (triggerRef.current?.contains(target)) return
      if (menuRef.current?.contains(target)) return
      close(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open])

  const todayIso = isoOf(today())

  /** The arrows and the title follow the panel: months on the day grid, years on
   *  the month grid, twelve-year pages on the year grid. */
  const head = (() => {
    const arrow = (delta: () => void, label: string, previous: boolean) => (
      <button type="button" className="datefield__nav" aria-label={label} onClick={delta}>
        <Icon
          name="chevron"
          size={16}
          className={`datefield__nav-icon${previous ? ' datefield__nav-icon--prev' : ''}`}
        />
      </button>
    )

    if (panel === 'years') {
      return (
        <>
          {arrow(() => shiftYearPage(-1), t('date.prevYears'), true)}
          <span id={titleId} className="datefield__title">
            {yearPageStart}–{yearPageStart + PICK_PAGE - 1}
          </span>
          {arrow(() => shiftYearPage(1), t('date.nextYears'), false)}
        </>
      )
    }

    if (panel === 'months') {
      return (
        <>
          {arrow(() => shiftYear(-1), t('date.prevYear'), true)}
          <span id={titleId} className="datefield__title">
            {view.y}
          </span>
          {arrow(() => shiftYear(1), t('date.nextYear'), false)}
        </>
      )
    }

    return (
      <>
        {arrow(() => shiftMonth(-1), t('date.prevMonth'), true)}
        <span id={titleId} className="datefield__title">
          <button
            type="button"
            className="datefield__title-button"
            aria-label={t('date.pickMonth')}
            onClick={() => setPanel('months')}
          >
            {monthTitle}
          </button>
          <button
            type="button"
            className="datefield__title-button"
            aria-label={t('date.pickYear')}
            onClick={() => setPanel('years')}
          >
            {view.y}
          </button>
        </span>
        {arrow(() => shiftMonth(1), t('date.nextMonth'), false)}
      </>
    )
  })()

  const menu = open
    ? createPortal(
        <div
          ref={menuRef}
          id={menuId}
          role="dialog"
          aria-modal="false"
          aria-labelledby={titleId}
          className="datefield__menu"
          style={
            position === null
              ? { position: 'fixed', top: 0, left: 0, visibility: 'hidden' }
              : {
                  position: 'fixed',
                  top: position.top,
                  left: position.left,
                  maxHeight: position.maxHeight,
                }
          }
          onKeyDown={onKeyDown}
        >
          <div className="datefield__head">{head}</div>

          {panel === 'months' ? (
            <div role="grid" aria-label={t('date.pickMonth')} className="datefield__pick">
              {monthNames.map((name, month) => (
                <button
                  key={month}
                  ref={(node) => {
                    if (node) monthRefs.current.set(month, node)
                    else monthRefs.current.delete(month)
                  }}
                  type="button"
                  role="gridcell"
                  tabIndex={month === view.m ? 0 : -1}
                  aria-selected={month === view.m}
                  className={[
                    'datefield__cell',
                    'datefield__month',
                    month === view.m ? 'datefield__cell--selected' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => chooseMonth(month)}
                >
                  {name}
                </button>
              ))}
            </div>
          ) : null}

          {panel === 'years' ? (
            <div role="grid" aria-label={t('date.pickYear')} className="datefield__pick">
              {Array.from({ length: PICK_PAGE }, (_, offset) => yearPageStart + offset).map((year) => (
                <button
                  key={year}
                  ref={(node) => {
                    if (node) yearRefs.current.set(year, node)
                    else yearRefs.current.delete(year)
                  }}
                  type="button"
                  role="gridcell"
                  tabIndex={year === view.y ? 0 : -1}
                  aria-selected={year === view.y}
                  className={[
                    'datefield__cell',
                    'datefield__year',
                    year === view.y ? 'datefield__cell--selected' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => chooseYear(year)}
                >
                  {year}
                </button>
              ))}
            </div>
          ) : null}

          {panel === 'days' ? (
            <>
              <div className="datefield__weekdays" aria-hidden="true">
                {months.weekdays.map((weekday) => (
                  <span key={weekday} className="datefield__weekday">
                    {weekday}
                  </span>
                ))}
              </div>

          <div role="grid" className="datefield__grid">
                {months.weeks.map((week) => (
                  <div role="row" key={week[0]?.iso ?? 'week'} className="datefield__week">
                    {week.map((day) => {
                      const blocked = isBlocked(day.parts)
                      return (
                        <button
                          key={day.iso}
                          ref={(node) => {
                            if (node) dayRefs.current.set(day.iso, node)
                            else dayRefs.current.delete(day.iso)
                          }}
                          type="button"
                          role="gridcell"
                          tabIndex={day.iso === cursor ? 0 : -1}
                          aria-selected={day.iso === props.value}
                          aria-current={day.iso === todayIso ? 'date' : undefined}
                          aria-disabled={blocked || undefined}
                          className={[
                            'datefield__day',
                            !day.inMonth ? 'datefield__day--outside' : '',
                            day.iso === todayIso ? 'datefield__day--today' : '',
                            day.iso === props.value ? 'datefield__day--selected' : '',
                          ]
                            .filter(Boolean)
                            .join(' ')}
                          onClick={() => {
                            if (!blocked) pick(day.parts)
                          }}
                        >
                          {day.parts.d}
                        </button>
                      )
                    })}
                  </div>
                ))}
              </div>

              {withTime ? (
                /* Two scrolling columns, hours beside minutes - the shape the native
                   picker used and the one people already know. Native controls are
                   ruled out: this picker exists because the browser draws its own and
                   will not be themed, and `input[type=time]` is drawn by the same
                   hand. */
                <div className="datefield__clock">
                  <ClockColumn
                    id={hoursId}
                    label={t('date.hour')}
                    values={HOURS}
                    selected={clock.h}
                    onPick={(value) => commitClock({ ...clockRef.current, h: value })}
                  />
                  <ClockColumn
                    id={minutesId}
                    label={t('date.minute')}
                    values={minutesFor(clock.m)}
                    selected={clock.m}
                    onPick={(value) => commitClock({ ...clockRef.current, m: value })}
                  />
                </div>
              ) : null}
            </>
          ) : null}

          <div className="datefield__foot">
            <button
              type="button"
              className="datefield__action"
              onClick={() => pick(today())}
            >
              {t('date.today')}
            </button>
            {props.value ? (
              <button
                type="button"
                className="datefield__action"
                onClick={() => {
                  props.onChange(null)
                  close(true)
                }}
              >
                {t('date.clear')}
              </button>
            ) : null}
          </div>
        </div>,
        document.body,
      )
    : null

  return (
    <>
      <button
        ref={triggerRef}
        id={props.id}
        type="button"
        className={`datefield__trigger${props.className ? ` ${props.className}` : ''}`}
        disabled={!openable}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-invalid={props.invalid || undefined}
        aria-label={props['aria-label'] ?? (props.value ? undefined : t('date.open'))}
        onClick={() => (open ? close(false) : show())}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault()
            show()
          }
        }}
      >
        <span className={props.value ? 'datefield__value' : 'datefield__value datefield__value--empty'}>
          {triggerText}
        </span>
        <Icon name="calendar" size={16} className="datefield__icon" />
      </button>
      {menu}
    </>
  )
}

/**
 * Arrow keys walk a grid of buttons by moving DOM focus, the way the clock
 * columns already do. Returns whether the key was one of them, so the caller can
 * leave the rest of the keyboard alone.
 *
 * The focus anchor stays the value, not the focus: walking over a month must not
 * change anything, which is why this moves focus instead of state.
 */
function stepFocus(event: React.KeyboardEvent, columns: number): boolean {
  const keys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End']
  if (!keys.includes(event.key)) return false
  event.preventDefault()
  event.stopPropagation()
  const items = [...((event.target as HTMLElement).closest('[role="grid"]')?.querySelectorAll('button') ?? [])]
  const at = items.indexOf(document.activeElement as HTMLButtonElement)
  const step =
    event.key === 'ArrowUp'
      ? -columns
      : event.key === 'ArrowDown'
        ? columns
        : event.key === 'ArrowLeft'
          ? -1
          : 1
  const next =
    event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? items.length - 1
        : Math.min(items.length - 1, Math.max(0, (at < 0 ? 0 : at) + step))
  items[next]?.focus()
  return true
}

/**
 * Where the popup sits: below the field when it fits, above it otherwise,
 * clamped to the viewport so a field near the right edge does not push it off.
 */
function computePosition(rect: DOMRect, height: number, width: number): MenuPosition {
  const spaceBelow = window.innerHeight - rect.bottom - MENU_GAP
  const spaceAbove = rect.top - MENU_GAP
  const above = height > spaceBelow && spaceAbove > spaceBelow
  const available = Math.max(above ? spaceAbove : spaceBelow, 0)
  // The clamp asks about the panel's own width, not the trigger's. The calendar
  // is wider than the field that opened it, so clamping by the trigger width
  // places a panel that does not fit: at the right-hand edge it ran off the
  // screen by exactly the difference between the two widths.
  const left = Math.max(EDGE_GAP, Math.min(rect.left, window.innerWidth - width - EDGE_GAP))
  return {
    top: above ? rect.top - MENU_GAP - Math.min(height, available) : rect.bottom + MENU_GAP,
    left,
    maxHeight: available,
  }
}

interface MonthCell {
  iso: string
  parts: DateParts
  inMonth: boolean
}

interface Month {
  weekdays: string[]
  weeks: MonthCell[][]
}

function buildMonth(year: number, month: number, locale: string): Month {
  const first = new Date(year, month, 1)
  // Monday-first: the ISO order, and what a Russian week starts with.
  const leading = (first.getDay() + 6) % DAYS_IN_WEEK
  const start = new Date(year, month, 1 - leading)

  const weekdays: string[] = []
  // Any fixed Monday-to-Sunday week will do for the header: only the weekday
  // name matters, not the date it fell on.
  for (let index = 0; index < DAYS_IN_WEEK; index++) {
    const day = new Date(2026, 9, 5 + index)
    weekdays.push(
      new Intl.DateTimeFormat(locale, { weekday: 'short' }).format(day).replace('.', ''),
    )
  }

  const weeks: MonthCell[][] = []
  for (let week = 0; week < WEEKS; week++) {
    const row: MonthCell[] = []
    for (let day = 0; day < DAYS_IN_WEEK; day++) {
      const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + week * DAYS_IN_WEEK + day)
      const parts = { y: date.getFullYear(), m: date.getMonth(), d: date.getDate() }
      const iso = isoOf(parts)
      row.push({ iso, parts, inMonth: date.getMonth() === month })
    }
    weeks.push(row)
  }
  return { weekdays, weeks }
}

function formatDate(parts: DateParts, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(new Date(parts.y, parts.m, parts.d))
}

interface Clock {
  h: number
  m: number
}

const HOURS = Array.from({ length: 24 }, (_, hour) => hour)

/**
 * Minutes on a five-minute grid, the way a clock is read.
 *
 * A value already in use that is not on the grid is added rather than rounded:
 * somebody who set 18:37 and reopens the field should see 37, not have it
 * quietly become 35 and then be saved as 35.
 */
function minutesFor(current: number): number[] {
  const minutes = Array.from({ length: 12 }, (_, step) => step * 5)
  if (current % 5 !== 0 && current >= 0 && current <= 59) {
    minutes.push(current)
    minutes.sort((a, b) => a - b)
  }
  return minutes
}

/**
 * One column of the clock: hours beside minutes.
 *
 * Roving tabindex inside the column - one stop for the reader, arrows within -
 * because a column of 24 separate tab stops would bury the calendar underneath.
 * Arrows move the focus only; a value is committed by a click or by Enter, so
 * nobody changes an hour by scrolling past it.
 */
function ClockColumn({
  id,
  label,
  values,
  selected,
  onPick,
}: {
  id: string
  label: string
  values: number[]
  selected: number
  onPick: (value: number) => void
}) {
  const listRef = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    listRef.current?.querySelector('[data-selected="true"]')?.scrollIntoView({ block: 'nearest' })
  }, [selected])

  return (
    <div className="datefield__clock-col">
      <div className="datefield__clock-head" id={id}>
        {label}
      </div>
      <div
        ref={listRef}
        className="datefield__clock-list"
        role="listbox"
        aria-labelledby={id}
        onKeyDown={(event) => {
          const keys = ['ArrowDown', 'ArrowRight', 'ArrowUp', 'ArrowLeft', 'Home', 'End']
          if (!keys.includes(event.key)) return
          event.preventDefault()
          event.stopPropagation()
          const items = [...(listRef.current?.querySelectorAll('button') ?? [])]
          const at = items.indexOf(document.activeElement as HTMLButtonElement)
          const step = event.key === 'ArrowUp' || event.key === 'ArrowLeft' ? -1 : 1
          const next =
            event.key === 'Home'
              ? 0
              : event.key === 'End'
                ? items.length - 1
                : Math.min(items.length - 1, Math.max(0, (at < 0 ? 0 : at) + step))
          items[next]?.focus()
        }}
      >
        {values.map((value) => (
          <button
            key={value}
            type="button"
            role="option"
            aria-selected={value === selected}
            data-selected={value === selected ? 'true' : undefined}
            tabIndex={value === selected ? 0 : -1}
            className={
              value === selected
                ? 'datefield__clock-item datefield__clock-item--selected'
                : 'datefield__clock-item'
            }
            onClick={() => onPick(value)}
          >
            {pad2(value)}
          </button>
        ))}
      </div>
    </div>
  )
}

/**
 * The day the value points at, whether it is a bare date or an instant.
 *
 * An instant is read in the reader's own zone on purpose: a deadline stored as
 * `2026-10-08T22:00:00Z` is the 8th at 18:00 in UTC+3, and showing it as the 8th
 * is what the person who set it meant.
 */
function selectedParts(props: DateFieldProps): DateParts | null {
  if (!props.value) return null
  if (props.withTime === true) {
    const parsed = new Date(props.value)
    if (Number.isNaN(parsed.getTime())) return null
    return { y: parsed.getFullYear(), m: parsed.getMonth(), d: parsed.getDate() }
  }
  return parseIso(props.value)
}

/** The clock the popup opens with: the value's own, or the caller's default. */
function clockOf(props: DateFieldProps): Clock {
  if (props.withTime === true && props.value) {
    const parsed = new Date(props.value)
    if (!Number.isNaN(parsed.getTime())) return { h: parsed.getHours(), m: parsed.getMinutes() }
  }
  return props.timeDefault === 'now'
    ? (() => {
        const now = new Date()
        return { h: now.getHours(), m: now.getMinutes() }
      })()
    : { h: 23, m: 59 }
}

/**
 * A day and a clock as the UTC instant the API stores.
 *
 * The wall-clock reading is converted rather than appended: `Date.UTC` would read
 * the numbers as UTC and shift the value by this machine's offset, which is the
 * bug that turns 18:00 into 06:00 either side of Greenwich.
 */
function toInstant(parts: DateParts, clock: Clock): string {
  return new Date(parts.y, parts.m, parts.d, clock.h, clock.m, 0, 0).toISOString()
}

function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

function isoOf(parts: DateParts): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${parts.y}-${pad(parts.m + 1)}-${pad(parts.d)}`
}

/** `YYYY-MM-DD` to local parts, or null for anything unparseable. */
function parseIso(value: string | null | undefined): DateParts | null {
  if (!value) return null
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim())
  if (!match) return null
  const parts = { y: Number(match[1]), m: Number(match[2]) - 1, d: Number(match[3]) }
  // Round-trip guard: 2026-02-31 is not a date, and silently reading it as
  // 3 March is how a deadline drifts.
  return isoOf(parts) === value.trim() ? parts : null
}

function today(): DateParts {
  const now = new Date()
  return { y: now.getFullYear(), m: now.getMonth(), d: now.getDate() }
}

function startOfMonth(parts: DateParts): DateParts {
  return { y: parts.y, m: parts.m, d: 1 }
}

function addDays(parts: DateParts, delta: number): DateParts {
  const date = new Date(parts.y, parts.m, parts.d + delta)
  return { y: date.getFullYear(), m: date.getMonth(), d: date.getDate() }
}

function startOfWeek(parts: DateParts): DateParts {
  return addDays(parts, -((new Date(parts.y, parts.m, parts.d).getDay() + 6) % DAYS_IN_WEEK))
}

function endOfWeek(parts: DateParts): DateParts {
  return startOfWeek(addDays(parts, DAYS_IN_WEEK - 1))
}

function daysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate()
}