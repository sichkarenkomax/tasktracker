import { useId, useState } from 'react'

import { useI18n } from '../i18n'
import { Icon } from '../layout/Icon'
import { reorder } from './columns'
import type { ColumnSet } from './columns'
import { Popover } from './Popover'

/**
 * Column chooser with drag-and-drop reordering.
 *
 * Built on the native HTML5 drag events rather than a library: it is a single
 * flat list of ten items, and a drag library would be the largest dependency in
 * the frontend for one panel. Every item also carries explicit up and down
 * buttons, because drag-and-drop is unusable with a keyboard and a settings
 * panel that cannot be operated without a mouse is not finished.
 *
 * Generic over the column set, because the task list and the people list both
 * offer this and neither of them should own it.
 *
 * It floats above the table rather than sitting in the page flow. In the flow it
 * pushed the table down by the height of the list every time it opened, so
 * choosing a column moved the rows out from under the reader - and the reader
 * who came to check a column order found the order they were checking gone. The
 * popover is anchored to the button that opened it, and `Popover` is the same
 * mechanism `Listbox` and `DateField` use, rather than a third implementation of
 * it.
 */
export function ColumnSettingsPanel<Id extends string>({
  set,
  columns,
  onChange,
  anchorRef,
  onClose,
}: {
  set: ColumnSet<Id>
  columns: Id[]
  onChange: (next: Id[]) => void
  /** The button this panel belongs to: it is positioned against it, and it is
   *  where the focus goes back to when the panel closes. */
  anchorRef: React.RefObject<HTMLElement | null>
  onClose: () => void
}) {
  const { t } = useI18n()
  const titleId = useId()
  const [dragging, setDragging] = useState<Id | null>(null)
  const [over, setOver] = useState<Id | null>(null)

  const required = set.required ?? new Set<Id>()
  const visible = new Set(columns)
  const hidden = set.ids.filter((id) => !visible.has(id))

  function move(id: Id, offset: number) {
    const from = columns.indexOf(id)
    const to = from + offset
    if (from === -1 || to < 0 || to >= columns.length) return
    const next = [...columns]
    const [moved] = next.splice(from, 1)
    if (moved === undefined) return
    next.splice(to, 0, moved)
    onChange(next)
  }

  function commitDrop(target: Id) {
    if (dragging && dragging !== target) {
      onChange(reorder(columns, dragging, target))
    }
    setDragging(null)
    setOver(null)
  }

  return (
    <Popover open anchorRef={anchorRef} onClose={onClose} labelledBy={titleId} className="column-settings">
      <div className="column-settings__head">
        <h2 id={titleId}>{t('columns.configure')}</h2>
        <button type="button" className="link" onClick={() => onChange([...set.defaults])}>
          {t('columns.reset')}
        </button>
      </div>
      <p className="muted">{t('columns.hint')}</p>

      <ol className="column-settings__list">
        {columns.map((id, index) => (
          <li
            key={id}
            className={
              over === id ? 'column-settings__item column-settings__item--over' : 'column-settings__item'
            }
            draggable
            onDragStart={() => setDragging(id)}
            onDragOver={(event) => {
              event.preventDefault()
              if (over !== id) setOver(id)
            }}
            onDragLeave={() => setOver((current) => (current === id ? null : current))}
            onDrop={(event) => {
              event.preventDefault()
              commitDrop(id)
            }}
            onDragEnd={() => {
              setDragging(null)
              setOver(null)
            }}
          >
            <span className="column-settings__grip" aria-hidden="true">
              <Icon name="grip" size={16} />
            </span>
            <span className="column-settings__label">{set.labels[id]}</span>
            <span className="column-settings__move">
              {/* Chevrons rather than the ↑ and ↓ characters: a glyph drawn from
                  the text font sits on a different baseline in every browser and
                  at every zoom level, and this is a control people aim at with a
                  mouse. The turned chevron is the same path, rotated. */}
              <button
                type="button"
                className="icon-button"
                aria-label={`${t('columns.title')}: ${set.labels[id]} ↑`}
                disabled={index === 0}
                onClick={() => move(id, -1)}
              >
                <Icon name="chevron" size={14} className="column-settings__chevron-up" />
              </button>
              <button
                type="button"
                className="icon-button"
                aria-label={`${t('columns.title')}: ${set.labels[id]} ↓`}
                disabled={index === columns.length - 1}
                onClick={() => move(id, 1)}
              >
                <Icon name="chevron" size={14} />
              </button>
              {required.has(id) ? null : (
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`${t('app.delete')}: ${set.labels[id]}`}
                  onClick={() => onChange(columns.filter((column) => column !== id))}
                >
                  <Icon name="close" size={14} />
                </button>
              )}
            </span>
          </li>
        ))}
      </ol>

      {hidden.length > 0 ? (
        <div className="column-settings__hidden">
          <span className="muted">{t('app.more')}</span>
          <div className="column-settings__chips">
            {hidden.map((id) => (
              <button
                key={id}
                type="button"
                className="chip chip--button"
                onClick={() => onChange([id, ...columns])}
              >
                <Icon name="plus" size={13} />
                {set.labels[id]}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </Popover>
  )
}