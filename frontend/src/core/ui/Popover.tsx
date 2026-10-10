import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

/**
 * A panel that floats above the page instead of pushing it down (stage 2.9).
 *
 * Written because the same thing already existed twice in this codebase - once
 * in `Listbox`, once in `DateField` - with the same eight lines of CSS, the same
 * three effects and the same positioning arithmetic copied alongside. A third
 * copy for the column chooser would have been a fourth place to fix every time
 * a popover needed to respect the window edge.
 *
 * What it does, and why each part is here:
 *
 * - **A portal into `document.body`.** A panel inside a scrolling table would be
 *   cut off by whatever clips its parent, which is the usual reason a popover
 *   "disappears" halfway down a list.
 * - **`position: fixed` with flip and clamp.** Measured from the trigger and
 *   recomputed on scroll and resize, so it follows the button when the page
 *   moves and turns upward rather than leaving the screen when there is no room
 *   below.
 * - **Hidden until measured.** The first frame has no coordinates yet, and
 *   `focus()` on an element that is still hidden is a no-op - so measuring first
 *   is what lets the panel take the focus on the same paint it appears.
 * - **Focus inside.** Unlike the listbox, whose rows are not focusable and whose
 *   focus never leaves the trigger, this panel holds real buttons. So it takes
 *   focus itself, `Escape` closes it and hands the focus back, and `Tab` lets it
 *   fold away rather than trapping the keyboard inside.
 * - **`mousedown`, not `click`,** for the outside press: the decision has to land
 *   before whatever was clicked on takes focus, or the click is swallowed by the
 *   element that was closing.
 */
const MENU_GAP = 6
const EDGE_GAP = 8

interface Position {
  top: number
  left: number
  maxHeight: number
}

function computePosition(
  rect: DOMRect,
  size: { height: number; width: number },
  align: 'start' | 'end',
): Position {
  const spaceBelow = window.innerHeight - rect.bottom - MENU_GAP
  const spaceAbove = rect.top - MENU_GAP
  // Upward only when below is genuinely too small *and* above is roomier: a
  // panel that flips because it is a centimetre tall would jump under the mouse.
  const above = size.height > spaceBelow && spaceAbove > spaceBelow
  const available = Math.max(above ? spaceAbove : spaceBelow, 0)
  const shown = size.height > 0 ? Math.min(size.height, available) : available
  const preferredLeft = align === 'end' ? rect.right - size.width : rect.left
  const left = Math.max(
    EDGE_GAP,
    Math.min(preferredLeft, window.innerWidth - size.width - EDGE_GAP),
  )
  return {
    top: above ? rect.top - MENU_GAP - shown : rect.bottom + MENU_GAP,
    left,
    maxHeight: shown,
  }
}

export function Popover({
  open,
  anchorRef,
  onClose,
  children,
  className,
  labelledBy,
  align = 'start',
}: {
  open: boolean
  anchorRef: React.RefObject<HTMLElement | null>
  onClose: () => void
  children: React.ReactNode
  className?: string
  /** The heading inside the panel, for a screen reader to read on arrival. */
  labelledBy?: string
  align?: 'start' | 'end'
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState<Position | null>(null)
  const restoreFocusRef = useRef(false)
  const id = useId()

  const close = useCallback(
    (restoreFocus: boolean) => {
      // Set before the close, because the effect below runs after the render
      // that the close causes - and the trigger may still be settling, so it is
      // retried until it takes the focus rather than only attempted once.
      restoreFocusRef.current = restoreFocus
      onClose()
    },
    [onClose],
  )

  const measure = useCallback(() => {
    const panel = panelRef.current
    const anchor = anchorRef.current
    if (!panel || !anchor) return
    setPosition(
      computePosition(
        anchor.getBoundingClientRect(),
        { height: panel.offsetHeight, width: panel.offsetWidth },
        align,
      ),
    )
  }, [align, anchorRef])

  useLayoutEffect(() => {
    if (!open) {
      setPosition(null)
      return
    }
    measure()
    panelRef.current?.focus()
  }, [open, measure])

  useEffect(() => {
    if (!open) return
    const reposition = () => measure()
    // Capture, so scrolling the table underneath counts as scrolling the page:
    // the panel is in the body while the thing it belongs to is not.
    window.addEventListener('scroll', reposition, true)
    window.addEventListener('resize', reposition)
    return () => {
      window.removeEventListener('scroll', reposition, true)
      window.removeEventListener('resize', reposition)
    }
  }, [open, measure])

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node | null
      if (!target) return
      if (anchorRef.current?.contains(target)) return
      if (panelRef.current?.contains(target)) return
      close(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        close(true)
      } else if (event.key === 'Tab') {
        // Natural tab order has to be able to leave, so the panel folds without
        // holding the keyboard inside it.
        close(false)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open, close, anchorRef])

  useLayoutEffect(() => {
    if (!restoreFocusRef.current) return
    const anchor = anchorRef.current
    if (!anchor || !anchor.isConnected) return
    restoreFocusRef.current = false
    anchor.focus()
  })

  if (!open) return null

  return createPortal(
    <div
      ref={panelRef}
      id={id}
      role="dialog"
      aria-labelledby={labelledBy}
      tabIndex={-1}
      className={className ? `popover ${className}` : 'popover'}
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
    >
      {children}
    </div>,
    document.body,
  )
}