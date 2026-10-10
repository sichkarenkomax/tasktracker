import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n'
import { Listbox } from '../ui/Listbox'
import {
  applyMask,
  countryCodes,
  countryHint,
  countryName,
  formatPhone,
  isValidPhone,
  phoneDigits,
} from './phoneMask'
import type { CountryCode } from 'libphonenumber-js'
import type { PhoneKind } from './phoneMask'

/**
 * A number, its country and what it is for (stage 2.8).
 *
 * One component for two screens - a person's own contacts and the
 * administrator's editor of somebody else's - because a number typed in one and
 * a number typed in the other are the same question, and two copies of it would
 * drift within a week.
 *
 * **The number is on its own line, and it is the wide one.** It used to share a
 * row with the kind and a button, which left about eleven characters of room for
 * a number that is thirteen long at the end - a field that is too narrow is a
 * field a person gives up on. The two lists sit under it, side by side, because
 * they are short and because reading "Russia / Work" together is the whole idea.
 *
 * The country is a real field rather than a setting somewhere, because the mask
 * cannot be right without it: `8 900 123-45-67` and `890 012 3456` are the same
 * call written two ways, and the library only knows which is which once the
 * country is named. The default is Russia - the portal's own language is Russian,
 * so that is the least surprising thing for the first person to type - and
 * changing it re-masks whatever is already typed.
 */
export interface PhoneDraft {
  number: string
  country: string
  kind: PhoneKind
}

/** Where the list starts, and what a new row looks like. */
export const DEFAULT_COUNTRY = 'RU'
export const NEW_PHONE: PhoneDraft = { number: '', country: DEFAULT_COUNTRY, kind: 'work' }

export function PhoneFields({
  value,
  onChange,
  disabled,
  id,
  numberPlaceholder,
}: {
  value: PhoneDraft
  onChange: (next: PhoneDraft) => void
  disabled?: boolean
  id?: string
  numberPlaceholder?: string
}) {
  const { t, locale } = useI18n()

  const filled = phoneDigits(value.number) !== ''
  const incomplete = filled && !isValidPhone(value.number, value.country)
  const hintId = `${id ?? 'phone'}-hint`

  return (
    <div className="phone-fields">
      <label className="field phone-fields__number">
        <span className="visually-hidden">{t('profile.phoneNumber')}</span>
        <input
          id={id}
          type="tel"
          inputMode="tel"
          autoComplete="off"
          disabled={disabled}
          placeholder={numberPlaceholder ?? t('profile.phoneNumberHint')}
          value={value.number}
          aria-invalid={incomplete || undefined}
          aria-describedby={incomplete ? hintId : undefined}
          onChange={(event) =>
            onChange({ ...value, number: applyMask(event.target.value, value.country) })
          }
        />
        {incomplete ? (
          <span className="field__error" id={hintId} role="status">
            {t('profile.phoneIncomplete')}
          </span>
        ) : null}
      </label>

      <div className="phone-fields__below">
        <label className="field phone-fields__country">
          <span className="visually-hidden">{t('profile.phoneCountry')}</span>
          <Listbox<string>
            value={value.country}
            disabled={disabled}
            searchable
            searchPlaceholder={t('listbox.searchPlaceholder')}
            nothingFoundLabel={t('listbox.nothingFound')}
            options={countryCodes().map((code) => ({
              value: code as string,
              // The platform's own names, in the interface's own language: no
              // country table of ours to translate and keep in step.
              label: countryName(code, locale),
              hint: countryHint(code),
            }))}
            onChange={(next) => {
              if (next === null) return
              // Re-mask what is already typed: the digits are the same call and
              // the country's shape of them has just changed.
              onChange({ ...value, country: next, number: applyMask(value.number, next) })
            }}
          />
        </label>

        <label className="field phone-fields__kind">
          <span className="visually-hidden">{t('profile.phoneKind')}</span>
          <Listbox<PhoneKind>
            value={value.kind}
            disabled={disabled}
            options={(['work', 'home', 'mobile', 'other'] as PhoneKind[]).map((kind) => ({
              value: kind,
              label: t(`profile.kind.${kind}` as TranslationKey),
            }))}
            onChange={(next) => {
              if (next !== null) onChange({ ...value, kind: next })
            }}
          />
        </label>
      </div>
    </div>
  )
}

/** A number with its country and kind, for the places that only read. */
export function PhoneLine({
  number,
  kind,
  country,
}: {
  number: string
  kind: PhoneKind | string
  country?: string | null
}) {
  const { t, locale } = useI18n()
  const known = (['work', 'home', 'mobile', 'other'] as const).includes(kind as PhoneKind)
  return (
    <span className="phone-line">
      <a href={`tel:${phoneDigits(number)}`}>{formatPhone(number, country)}</a>{' '}
      <span className="muted">
        {known ? t(`profile.kind.${kind}` as TranslationKey) : kind}
        {country ? ` · ${countryName(country as CountryCode, locale)}` : ''}
      </span>
    </span>
  )
}
