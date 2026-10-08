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
  /** `YYYY-MM-DD`, or null/'' for "not set". */
  value: string | null
  onChange: (next: string | null) => void

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

export function DateField(props: DateFieldProps) {
  const { locale, t } = useI18n()
  const [open, setOpen] = useState(false)
  const [view, setView] = useState<DateParts>(() => startOfMonth(parseIso(props.value) ?? today()))
  const [cursor, setCursor] = useState<string>(() => isoOf(parseIso(props.value) ?? today()))
  const [position, setPosition] = useState<MenuPosition | null>(null)

  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const dayRefs = useRef(new Map<string, HTMLButtonElement>())
  const restoreFocusRef = useRef(false)
  const reactId = useId()

  const menuId = `datefield-${reactId}`
  const titleId = `${menuId}-title`

  const selected = parseIso(props.value)
  const placeholder = props.placeholder ?? t('date.placeholder')
  const openable = !props.disabled

  const months = useMemo(
    () => buildMonth(view.y, view.m, locale),
    [view.y, view.m, locale],
  )
  const title = useMemo(
    () => new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric' }).format(new Date(view.y, view.m, 1)),
    [locale, view.y, view.m],
  )
  const triggerText = selected ? formatDate(selected, locale) : placeholder

  function show() {
    const from = selected ?? today()
    setView(startOfMonth(from))
    setCursor(isoOf(from))
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
    props.onChange(isoOf(parts))
    close(true)
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

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
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
        const target = parseIso(cursor)
        if (target && !isBlocked(target)) pick(target)
        break
      }
      case 'Escape':
        event.preventDefault()
        close(true)
        break
      case 'Tab':
        // Let the browser move on: the popup folds, focus stays in the form.
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
    setPosition(computePosition(trigger.getBoundingClientRect(), menu.offsetHeight))
  }, [open])

  // The grid takes real focus on open, on the chosen day or on today.
  //
  // Not on the opening commit: the menu paints its first frame with
  // `visibility: hidden` (its position is only known after the measuring pass
  // above), and focus() on a hidden element is a silent no-op. Waiting for a
  // measured position is what makes the keyboard arrive inside the grid.
  useLayoutEffect(() => {
    if (!open || position === null) return
    dayRefs.current.get(cursor)?.focus()
  }, [open, position, cursor])

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
      setPosition(computePosition(trigger.getBoundingClientRect(), menu.offsetHeight))
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
          <div className="datefield__head">
            <button
              type="button"
              className="datefield__nav"
              aria-label={t('date.prevMonth')}
              onClick={() => shiftMonth(-1)}
            >
              <Icon name="chevron" size={16} className="datefield__nav-icon datefield__nav-icon--prev" />
            </button>
            <span id={titleId} className="datefield__title">
              {title}
            </span>
            <button
              type="button"
              className="datefield__nav"
              aria-label={t('date.nextMonth')}
              onClick={() => shiftMonth(1)}
            >
              <Icon name="chevron" size={16} className="datefield__nav-icon" />
            </button>
          </div>

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
 * Where the popup sits: below the field when it fits, above it otherwise,
 * clamped to the viewport so a field near the right edge does not push it off.
 */
function computePosition(rect: DOMRect, height: number): MenuPosition {
  const spaceBelow = window.innerHeight - rect.bottom - MENU_GAP
  const spaceAbove = rect.top - MENU_GAP
  const above = height > spaceBelow && spaceAbove > spaceBelow
  const available = Math.max(above ? spaceAbove : spaceBelow, 0)
  const left = Math.max(EDGE_GAP, Math.min(rect.left, window.innerWidth - rect.width - EDGE_GAP))
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