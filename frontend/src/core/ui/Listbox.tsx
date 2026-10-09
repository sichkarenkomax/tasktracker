import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { Icon } from '../layout/Icon'
import { Avatar } from '../users/Avatar'

/**
 * One row of the list.
 *
 * Mirrors what a native `<option>` could express: a value, a label, a tooltip
 * and whether the row may be chosen.
 */
export interface ListboxOption<T extends string> {
  value: T
  label: string
  /** The native `<option title>` equivalent - a tooltip explaining the row. */
  hint?: string
  disabled?: boolean
  /**
   * A person's picture (stage 2.4). The key is deliberately different from
   * "no picture": rows that are not people - a status, a project - never pass
   * it and get no thumbnail, while a member without a photo passes `null` and
   * gets the letter fallback, exactly as every other roster does.
   *
   * The native fallback on touch pointers cannot draw an image inside an
   * `<option>`; there the label alone carries the row, as before.
   */
  avatarUrl?: string | null
}

interface ListboxBaseProps<T extends string> {
  options: ReadonlyArray<ListboxOption<T>>

  /**
   * The trigger's text while nothing is selected, and the label of the
   * "nothing" row.
   *
   * The pair of flags below reproduces the two native patterns this replaces:
   * a blank option that is selectable (which makes the field clearable) and a
   * blank option that is disabled (a placeholder that must be replaced).
   */
  placeholder?: string
  clearable?: boolean

  disabled?: boolean
  /** Marks the control as holding a value the form will reject (native `required`). */
  invalid?: boolean

  /** Extra classes for the trigger - size and layout rules of the host page. */
  className?: string
  id?: string
  'aria-label'?: string
}

export interface SingleListboxProps<T extends string> extends ListboxBaseProps<T> {
  multiple?: false
  value: T | null
  onChange: (next: T | null) => void
}

export interface MultiListboxProps<T extends string> extends ListboxBaseProps<T> {
  multiple: true
  value: T[]
  onChange: (next: T[]) => void
}

export type ListboxProps<T extends string> = SingleListboxProps<T> | MultiListboxProps<T>

interface Row<T extends string> {
  value: T | null
  label: string
  hint?: string
  disabled: boolean
  clear: boolean
  avatarUrl?: string | null
}

interface MenuPosition {
  top: number
  left: number
  minWidth: number
  maxHeight: number
}

const MENU_GAP = 6
const EDGE_GAP = 8
const TYPEAHEAD_RESET_MS = 700

/**
 * A styled listbox in place of the native `<select>` (stage 1.3).
 *
 * The APG select-only combobox shape: a `<button>` that owns a portalled
 * `role="listbox"`, keyboard focus stays on the button and the highlighted row
 * is communicated with `aria-activedescendant`. Keeping focus on the button is
 * what makes Escape and typeahead work without a focus dance through a portal,
 * and the button is a labelable element - so every `<label>` wrapper written
 * for the old `<select>` keeps working unchanged.
 *
 * On touch pointers the component renders a native `<select>` instead: a custom
 * picker is strictly worse than the platform one where the platform already
 * draws its own wheel (the roadmap's stated v1 fallback).
 */
export function Listbox<T extends string>(props: ListboxProps<T>) {
  const [native] = useState(
    () =>
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(pointer: coarse)').matches,
  )
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const [position, setPosition] = useState<MenuPosition | null>(null)

  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  // The menu's natural size, measured once per opening: the flip and the max
  // height are decided from it without a second measuring pass on every scroll.
  const sizeRef = useRef({ height: 0, width: 0 })
  const typeRef = useRef({ buffer: '', at: 0 })
  const reactId = useId()

  const menuId = `listbox-${reactId}`
  const optionId = (index: number) => `${menuId}-option-${index}`

  // A blank row is only meaningful with a label to show it under.
  const clearable = props.clearable === true && props.placeholder !== undefined

  const rows: Array<Row<T>> = []
  if (props.placeholder !== undefined) {
    rows.push({
      value: null,
      label: props.placeholder,
      disabled: !clearable,
      clear: clearable,
    })
  }
  for (const option of props.options) {
    rows.push({
      value: option.value,
      label: option.label,
      hint: option.hint,
      disabled: option.disabled === true,
      clear: false,
      avatarUrl: option.avatarUrl,
    })
  }
  // "Empty" is a real state: with nothing selectable the trigger says so by
  // going inert rather than opening a list that cannot be chosen from.
  const openable = rows.some((row) => !row.disabled)

  const labelOf = new Map<T, string>(props.options.map((option) => [option.value, option.label]))

  let selectedValues: ReadonlyArray<T>
  let isSelected: (value: T | null) => boolean
  let triggerText: string
  // The selected person's picture in the trigger itself, so the closed control
  // reads as "this face" rather than a name that could belong to anybody.
  let triggerAvatar: string | null | undefined
  if (props.multiple) {
    const current: ReadonlyArray<T> = props.value
    selectedValues = current
    isSelected = (value) => value !== null && current.includes(value)
    triggerText = current.map((value) => labelOf.get(value) ?? value).join(', ')
    // Several faces in one trigger would be a row of thumbnails; the labels
    // already distinguish the people there.
    triggerAvatar = undefined
  } else {
    const current: T | null = props.value
    selectedValues = current === null ? [] : [current]
    isSelected = (value) => value === current
    triggerText =
      current !== null ? (labelOf.get(current) ?? current) : (props.placeholder ?? '')
    triggerAvatar =
      current !== null ? props.options.find((option) => option.value === current)?.avatarUrl : undefined
  }

  function pick(row: Row<T>) {
    if (row.disabled) return
    if (props.multiple) {
      if (row.value === null) {
        props.onChange([])
        return
      }
      const picked: T = row.value
      const current = props.value
      props.onChange(
        current.includes(picked) ? current.filter((value) => value !== picked) : [...current, picked],
      )
      // Multi stays open: choosing three people should not mean opening the
      // list three times.
      return
    }
    props.onChange(row.value)
    close(true)
  }

  function close(restoreFocus: boolean) {
    setOpen(false)
    if (restoreFocus) triggerRef.current?.focus()
  }

  function openMenu() {
    if (!openable) return
    const selectedRow = rows.findIndex(
      (row) => row.value !== null && selectedValues.includes(row.value),
    )
    const firstEnabled = rows.findIndex((row) => !row.disabled)
    setActiveIndex(selectedRow >= 0 ? selectedRow : firstEnabled)
    setOpen(true)
    // Safari does not focus buttons on click, and the keyboard handling below
    // lives on the button - focus it explicitly when the menu opens.
    triggerRef.current?.focus()
  }

  function step(delta: number) {
    let index = activeIndex
    for (let seen = 0; seen < rows.length; seen++) {
      index = (index + delta + rows.length) % rows.length
      const row = rows[index]
      if (row && !row.disabled) {
        setActiveIndex(index)
        return
      }
    }
  }

  function moveToEdge(edge: 'first' | 'last') {
    const index =
      edge === 'first'
        ? rows.findIndex((row) => !row.disabled)
        : rows.map((row) => row.disabled).lastIndexOf(false)
    if (index >= 0) setActiveIndex(index)
  }

  function findMatch(needle: string, from: number): number {
    for (let seen = 0; seen < rows.length; seen++) {
      const index = ((from + seen) % rows.length + rows.length) % rows.length
      const row = rows[index]
      if (!row || row.disabled) continue
      if (row.label.toLowerCase().startsWith(needle)) return index
    }
    return -1
  }

  function typeahead(char: string) {
    const now = Date.now()
    const continuing = now - typeRef.current.at < TYPEAHEAD_RESET_MS
    const buffer = (continuing ? typeRef.current.buffer + char : char).toLowerCase()
    typeRef.current = { buffer, at: now }

    // Repeating one letter walks through its matches; anything else starts a
    // fresh search from the top, because the buffer no longer matches the row
    // the cursor is on.
    const repeating = buffer.length > 1 && buffer.split('').every((item) => item === buffer[0])
    let found = findMatch(buffer, repeating ? activeIndex + 1 : 0)
    if (found < 0 && buffer.length > 1) {
      found = findMatch(buffer.charAt(buffer.length - 1), activeIndex + 1)
    }
    if (found >= 0) setActiveIndex(found)
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (props.disabled || !openable) return
    const key = event.key

    if (!open) {
      // Enter and Space open the button natively (a click); only the arrows are
      // ours to answer when closed.
      if (key === 'ArrowDown' || key === 'ArrowUp') {
        event.preventDefault()
        openMenu()
      }
      return
    }

    switch (key) {
      case 'Escape':
        event.preventDefault()
        close(true)
        break
      case 'Tab':
        // Natural tab order must continue out of the control, so the menu folds
        // without stealing or trapping the focus.
        setOpen(false)
        break
      case 'ArrowDown':
        event.preventDefault()
        step(1)
        break
      case 'ArrowUp':
        event.preventDefault()
        step(-1)
        break
      case 'Home':
        event.preventDefault()
        moveToEdge('first')
        break
      case 'End':
        event.preventDefault()
        moveToEdge('last')
        break
      case 'Enter':
      case ' ': {
        // Prevent default so the button's own click does not toggle the menu
        // back shut right after the selection.
        event.preventDefault()
        const row = rows[activeIndex]
        if (row) pick(row)
        break
      }
      default:
        if (key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
          typeahead(key)
        }
    }
  }

  // Measuring happens once per opening, before paint: the natural size decides
  // whether the menu flips above the trigger, and the flip is applied in the
  // same frame - the reader never sees the unflipped position.
  useLayoutEffect(() => {
    if (!open) {
      setPosition(null)
      return
    }
    const menu = menuRef.current
    const trigger = triggerRef.current
    if (!menu || !trigger) return
    sizeRef.current = { height: menu.offsetHeight, width: menu.offsetWidth }
    setPosition(computePosition(trigger.getBoundingClientRect(), sizeRef.current))
  }, [open])

  // The menu is portalled and `fixed`, so it tracks the trigger through the
  // page's scrolls (capture phase catches the scrolling table underneath) and
  // the window's resizes.
  useEffect(() => {
    if (!open) return
    const reposition = () => {
      const trigger = triggerRef.current
      if (!trigger) return
      setPosition(computePosition(trigger.getBoundingClientRect(), sizeRef.current))
    }
    window.addEventListener('scroll', reposition, true)
    window.addEventListener('resize', reposition)
    return () => {
      window.removeEventListener('scroll', reposition, true)
      window.removeEventListener('resize', reposition)
    }
  }, [open])

  // Clicking away closes the menu. Pointer events rather than click, so the
  // decision lands before whatever was clicked on takes focus.
  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node | null
      if (!target) return
      if (triggerRef.current?.contains(target)) return
      if (menuRef.current?.contains(target)) return
      setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open])

  // Keep the keyboard cursor visible when it walks off the visible slice.
  useLayoutEffect(() => {
    if (!open) return
    const active = menuRef.current?.querySelector('[data-active="true"]')
    active?.scrollIntoView({ block: 'nearest' })
  }, [open, activeIndex])

  if (native) {
    return (
      <select
        id={props.id}
        className={props.className}
        disabled={props.disabled}
        multiple={props.multiple === true}
        value={props.multiple === true ? props.value : (props.value ?? '')}
        aria-label={props['aria-label']}
        aria-invalid={props.invalid || undefined}
        onChange={(event) => {
          if (props.multiple === true) {
            const picked = Array.from(
              event.target.selectedOptions,
              (option) => option.value,
            ) as T[]
            props.onChange(picked)
          } else {
            props.onChange(event.target.value === '' ? null : (event.target.value as T))
          }
        }}
      >
        {props.placeholder !== undefined ? (
          <option value="" disabled={!clearable}>
            {props.placeholder}
          </option>
        ) : null}
        {props.options.map((option) => (
          <option
            key={option.value}
            value={option.value}
            title={option.hint}
            disabled={option.disabled}
          >
            {option.label}
          </option>
        ))}
      </select>
    )
  }

  const menu = open
    ? createPortal(
        <div
          ref={menuRef}
          id={menuId}
          role="listbox"
          aria-multiselectable={props.multiple === true || undefined}
          className="listbox__menu"
          style={
            position === null
              ? { position: 'fixed', top: 0, left: 0, visibility: 'hidden', maxHeight: 'none' }
              : {
                  position: 'fixed',
                  top: position.top,
                  left: position.left,
                  minWidth: position.minWidth,
                  maxHeight: position.maxHeight,
                }
          }
          // The menu holds no focusable nodes; without this a press on a row
          // would move focus to the document and the keyboard would go blind.
          onMouseDown={(event) => event.preventDefault()}
        >
          {rows.map((row, index) => (
            <div
              key={index}
              id={optionId(index)}
              role="option"
              aria-selected={isSelected(row.value)}
              aria-disabled={row.disabled || undefined}
              data-active={index === activeIndex ? 'true' : undefined}
              title={row.hint}
              className={[
                'listbox__option',
                index === activeIndex ? 'listbox__option--active' : '',
                isSelected(row.value) ? 'listbox__option--selected' : '',
                row.clear ? 'listbox__option--clear' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => pick(row)}
            >
              {row.avatarUrl !== undefined ? (
                <Avatar src={row.avatarUrl} name={row.label} size="sm" />
              ) : null}
              <span>{row.label}</span>
              {isSelected(row.value) && !row.clear ? (
                <Icon name="check" size={13} className="listbox__option-check" />
              ) : null}
            </div>
          ))}
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
        role="combobox"
        className={`listbox__trigger${props.className ? ` ${props.className}` : ''}`}
        disabled={props.disabled || !openable}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-activedescendant={open ? optionId(activeIndex) : undefined}
        aria-invalid={props.invalid || undefined}
        aria-label={props['aria-label']}
        onClick={() => (open ? close(false) : openMenu())}
        onKeyDown={onKeyDown}
      >
        {triggerAvatar !== undefined ? (
          <Avatar src={triggerAvatar} name={triggerText} size="sm" />
        ) : null}
        <span className="listbox__value">{triggerText}</span>
        <Icon name="chevron" size={14} className="listbox__chevron" />
      </button>
      {menu}
    </>
  )
}

/**
 * Where the menu sits relative to the trigger.
 *
 * Below when it fits, above when that is the larger remaining space, clamped to
 * the viewport horizontally so a trigger near the right edge does not push the
 * menu off-screen.
 */
function computePosition(rect: DOMRect, size: { height: number; width: number }): MenuPosition {
  const spaceBelow = window.innerHeight - rect.bottom - MENU_GAP
  const spaceAbove = rect.top - MENU_GAP
  const above = size.height > spaceBelow && spaceAbove > spaceBelow
  const available = Math.max(above ? spaceAbove : spaceBelow, 0)
  const shown = size.height > 0 ? Math.min(size.height, available) : available
  const width = Math.max(size.width, rect.width)
  const left = Math.max(
    EDGE_GAP,
    Math.min(rect.left, window.innerWidth - width - EDGE_GAP),
  )
  return {
    top: above ? rect.top - MENU_GAP - shown : rect.bottom + MENU_GAP,
    left,
    minWidth: rect.width,
    maxHeight: shown,
  }
}
