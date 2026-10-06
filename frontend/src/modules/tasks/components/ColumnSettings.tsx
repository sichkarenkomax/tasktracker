import { useState } from 'react'

import { useI18n } from '../../../core/i18n'
import { Icon } from '../../../core/layout/Icon'
import {
  COLUMN_IDS,
  COLUMN_LABELS,
  DEFAULT_COLUMNS,
  REQUIRED_COLUMNS,
  reorder,
} from './columns'
import type { ColumnId } from './columns'

/**
 * Column chooser with drag-and-drop reordering.
 *
 * Built on the native HTML5 drag events rather than a library: it is a single
 * flat list of ten items, and a drag library would be the largest dependency in
 * the frontend for one panel. Every item also carries explicit up and down
 * buttons, because drag-and-drop is unusable with a keyboard and a settings
 * panel that cannot be operated without a mouse is not finished.
 */
export function ColumnSettings({
  columns,
  onChange,
}: {
  columns: ColumnId[]
  onChange: (next: ColumnId[]) => void
}) {
  const { t } = useI18n()
  const [dragging, setDragging] = useState<ColumnId | null>(null)
  const [over, setOver] = useState<ColumnId | null>(null)

  const visible = new Set(columns)
  const hidden = COLUMN_IDS.filter((id) => !visible.has(id))

  function move(id: ColumnId, offset: number) {
    const from = columns.indexOf(id)
    const to = from + offset
    if (from === -1 || to < 0 || to >= columns.length) return
    const next = [...columns]
    const [moved] = next.splice(from, 1)
    if (moved === undefined) return
    next.splice(to, 0, moved)
    onChange(next)
  }

  function commitDrop(target: ColumnId) {
    if (dragging && dragging !== target) {
      onChange(reorder(columns, dragging, target))
    }
    setDragging(null)
    setOver(null)
  }

  return (
    <div className="panel column-settings">
      <div className="column-settings__head">
        <h2>{t('columns.configure')}</h2>
        <button type="button" className="link" onClick={() => onChange([...DEFAULT_COLUMNS])}>
          {t('columns.reset')}
        </button>
      </div>
      <p className="muted">{t('columns.hint')}</p>

      <ol className="column-settings__list">
        {columns.map((id, index) => (
          <li
            key={id}
            className={over === id ? 'column-settings__item column-settings__item--over' : 'column-settings__item'}
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
            <span className="column-settings__label">{t(COLUMN_LABELS[id])}</span>
            <span className="column-settings__move">
              <button
                type="button"
                className="icon-button"
                aria-label={`${t('columns.title')}: ${t(COLUMN_LABELS[id])} ↑`}
                disabled={index === 0}
                onClick={() => move(id, -1)}
              >
                ↑
              </button>
              <button
                type="button"
                className="icon-button"
                aria-label={`${t('columns.title')}: ${t(COLUMN_LABELS[id])} ↓`}
                disabled={index === columns.length - 1}
                onClick={() => move(id, 1)}
              >
                ↓
              </button>
              {REQUIRED_COLUMNS.has(id) ? null : (
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`${t('app.delete')}: ${t(COLUMN_LABELS[id])}`}
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
                {t(COLUMN_LABELS[id])}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}
