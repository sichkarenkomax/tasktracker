import { useEffect, useState } from 'react'

import { useI18n } from '../../../core/i18n'
import { Icon } from '../../../core/layout/Icon'
import { Listbox } from '../../../core/ui/Listbox'
import { DURATION_UNITS } from '../types'
import type { DurationUnit } from '../types'

/**
 * The planned window: when the work starts, how long it should take, and when
 * that puts the end.
 *
 * Three inputs rather than two date boxes, because a plan is written as "from
 * Monday, about three days" far more often than as two dates somebody had to work
 * out. The end is computed in the browser as a preview and again on the server,
 * where it is stored - two implementations of the same rule is a smell, so the
 * server's is the authority and this one is only there to show the consequence
 * before the request goes out.
 */
export function PlanningFields({
  start,
  end,
  duration,
  unit,
  disabled,
  onCommit,
}: {
  start: string | null
  end: string | null
  duration: number | null
  unit: DurationUnit
  disabled?: boolean
  onCommit: (body: {
    planned_start?: string | null
    planned_end?: string | null
    planned_duration?: number | null
    duration_unit?: DurationUnit
  }) => Promise<void>
}) {
  const { t } = useI18n()
  // `datetime-local` wants `YYYY-MM-DDTHH:mm` with no zone; the API wants an
  // instant. Converting between the two here is what keeps the server from having
  // to guess which of the two it was handed.
  const [draftStart, setDraftStart] = useState(toLocalInput(start))
  const [draftDuration, setDraftDuration] = useState(duration === null ? '' : String(duration))
  const [draftUnit, setDraftUnit] = useState<DurationUnit>(unit)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    setDraftStart(toLocalInput(start))
    setDraftDuration(duration === null ? '' : String(duration))
    setDraftUnit(unit)
  }, [start, duration, unit])

  const preview = computeEnd(draftStart, draftDuration, draftUnit)

  async function commit() {
    setPending(true)
    setError(null)
    try {
      await onCommit({
        // Empty means "no plan": an explicit null, which is the only way to clear a
        // nullable field. An untouched box must not be read as a change.
        planned_start: draftStart === '' ? null : new Date(draftStart).toISOString(),
        planned_duration: draftDuration === '' ? null : Number(draftDuration),
        duration_unit: draftUnit,
      })
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : t('error.generic'))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="planning">
      <label className="field">
        <span>{t('tasks.plannedStart')}</span>
        <input
          type="datetime-local"
          value={draftStart}
          disabled={disabled || pending}
          onChange={(event) => setDraftStart(event.target.value)}
        />
      </label>

      <label className="field planning__duration">
        <span>{t('tasks.plannedDuration')}</span>
        <input
          type="number"
          min={0}
          value={draftDuration}
          disabled={disabled || pending}
          onChange={(event) => setDraftDuration(event.target.value)}
        />
      </label>

      <label className="field">
        <span>{t('tasks.durationUnit')}</span>
        <Listbox<string>
          value={draftUnit}
          options={DURATION_UNITS.map((option) => ({
            value: option,
            label: t(`unit.${option}` as TranslationKey),
          }))}
          disabled={disabled || pending}
          onChange={(next) => {
            if (next !== null) setDraftUnit(next as DurationUnit)
          }}
        />
      </label>

      <div className="field">
        <span>{t('tasks.plannedEnd')}</span>
        <output className="planning__end">
          {end ? formatMoment(end) : preview ? `${formatMoment(preview)} (${t('tasks.preview')})` : EMPTY_END}
        </output>
      </div>

      <button
        type="button"
        className="button button--primary"
        disabled={disabled || pending}
        onClick={() => void commit()}
      >
        <Icon name="save" size={14} />
        {t('app.save')}
      </button>

      {error ? (
        <span className="field__error" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  )
}

const EMPTY_END = '—'

/**
 * An instant as `datetime-local` wants it: local wall-clock, no zone suffix.
 *
 * `toISOString()` would append a `Z` and shift the field by the offset, so a plan
 * set at 09:00 would come back as 06:00 for somebody east of Greenwich - an
 * invisible bug that only shows up in a country other than the author's.
 */
function toLocalInput(value: string | null): string {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}` +
    `T${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
  )
}

/**
 * A local copy of the server's duration arithmetic, for the preview only.
 *
 * Months are the awkward case and the reason this is written out rather than
 * delegated: a month is not 30 days, and using it as one drifts a plan by a
 * fortnight a year. The server stores the result, so a disagreement here is
 * visible as a wrong preview rather than as corrupted data.
 */
function computeEnd(
  start: string,
  duration: string,
  unit: DurationUnit,
): string | null {  if (start === '' || duration === '') return null
  const amount = Number(duration)
  if (!Number.isFinite(amount)) return null

  const from = new Date(start)
  if (Number.isNaN(from.getTime())) return null

  const to = new Date(from)
  switch (unit) {
    case 'minutes':
      to.setMinutes(to.getMinutes() + amount)
      break
    case 'hours':
      to.setHours(to.getHours() + amount)
      break
    case 'days':
      to.setDate(to.getDate() + amount)
      break
    case 'weeks':
      to.setDate(to.getDate() + amount * 7)
      break
    case 'months': {
      const day = to.getDate()
      to.setDate(1)
      to.setMonth(to.getMonth() + amount)
      // Clamp instead of overflowing: 31 January plus one month is the end of
      // February, not 3 March.
      to.setDate(Math.min(day, daysInMonth(to.getFullYear(), to.getMonth() + 1)))
      break
    }
    default:
      return null
  }
  return Number.isNaN(to.getTime()) ? null : to.toISOString()
}

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate()
}

function formatMoment(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? EMPTY_END : parsed.toLocaleString()
}

type TranslationKey = Parameters<ReturnType<typeof useI18n>['t']>[0]
