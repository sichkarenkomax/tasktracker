import {
  formatIncompletePhoneNumber,
  getCountries,
  getCountryCallingCode,
  parsePhoneNumberFromString,
} from 'libphonenumber-js/max'
import type { CountryCode } from 'libphonenumber-js'

/**
 * Phone numbers, formatted by country (stage 2.8).
 *
 * The grouping is Google's libphonenumber data rather than a rule of ours,
 * because "how is a number written in this country" is a table with a few
 * hundred rows that changes when somebody notices a new one, and a hand-written
 * rule is wrong for every country the author did not grow up in. That was the
 * whole objection to the mask this replaced.
 *
 * It is a local data file: 44 KB gzipped with every country, no network calls
 * and no account. The bundle it goes into was 108 KB gzipped, so this is a
 * visible weight and a deliberate one.
 *
 * A number is always *stored* in E.164 (`+79001234567`) and always *read* in the
 * country it belongs to. The country travels with the number, because a number
 * written nationally is unreadable without it: `8 900 123-45-67` is the same
 * call in three countries.
 */

/** The kinds the screen offers, in the order it offers them. */
export const PHONE_KINDS = ['work', 'home', 'mobile', 'other'] as const
export type PhoneKind = (typeof PHONE_KINDS)[number]

/** Digits and a leading plus, everything else dropped. */
export function phoneDigits(value: string): string {
  const plus = value.trimStart().startsWith('+') ? '+' : ''
  return plus + (value.match(/\d/g) ?? []).join('')
}

/** Every country, by its own two letters, for the listbox. */
export function countryCodes(): CountryCode[] {
  return getCountries()
}

/** The country's name in the interface's own language. */
export function countryName(code: CountryCode, locale: string): string {
  // `Intl.DisplayNames` is in the browser and in Node since 18, and using it
  // means no country-name table of our own to translate and keep current.
  try {
    return new Intl.DisplayNames([locale], { type: 'region' }).of(code) ?? code
  } catch {
    return code
  }
}

/** The number as it is read, in the country the person gave.
 *
 * A number that cannot be attributed to a country is shown as it was written:
 * guessing would put a foreign number in somebody's national format, which is
 * a wrong answer presented confidently.
 */
export function formatPhone(value: string, country?: string | null): string {
  const trimmed = value.trim()
  if (trimmed === '') return ''
  const region = (country ?? undefined) as CountryCode | undefined
  if (region) {
    const parsed = parse(phoneDigits(trimmed), region)
    if (parsed) return parsed.formatNational()
  }
  const parsedAny = parse(phoneDigits(trimmed))
  return parsedAny ? parsedAny.formatInternational() : phoneDigits(trimmed)
}

/**
 * One parse, used by reading, by validity and by storage.
 *
 * A leading `+` carries its own country, and passing a region as well would
 * quietly ignore it - which is right: the number knows better than the dropdown
 * does.
 */
function parse(text: string, country?: CountryCode) {
  return parsePhoneNumberFromString(
    text,
    text.startsWith('+') ? undefined : country,
  )
}

/**
 * The mask, applied while the person types.
 *
 * The library's own incomplete formatter, which follows the country's rule as
 * the digits arrive: typing a Russian number gives `8 (900) 123-45-67` step by
 * step and an American one `(415) 555-0100`, without this file knowing what a
 * Russian number looks like.
 *
 * When the prefix typed so far matches nothing in that country - a number from
 * somewhere the table has no rule for, or the first digit of a national number
 * that has not been recognised yet - the library leaves the digits alone. That
 * is the behaviour to keep: a mask that groups digits it does not understand
 * invents a format, and a person reading back what they typed is reading it from
 * the field.
 *
 * A leading `+` switches to the international branch, because that is what it
 * means: the country is in the number now and the field is not guessing.
 */
export function applyMask(value: string, country: string): string {
  const text = value.trim()
  if (text === '') return ''
  // A leading `+` means the country is already in the number, so the field's own
  // choice is not applied to it.
  if (text.startsWith('+')) {
    return formatIncompletePhoneNumber(text, undefined)
  }
  try {
    return formatIncompletePhoneNumber(text, { defaultCountry: country as CountryCode })
  } catch {
    // An unknown country code (a stale stored value, a mistyped listbox entry)
    // must not take the field down with it: the digits go in ungrouped and the
    // server is the one that refuses an impossible number.
    return phoneDigits(value)
  }
}

/** The country a person can be called on: what the platform calls it, and
 *  the digits that reach it. The two are shown together because the second is
 *  what somebody abroad reads first, and `+RU` would be no help to anybody. */
export function countryHint(code: string): string {
  try {
    return `+${getCountryCallingCode(code as CountryCode)}`
  } catch {
    return ''
  }
}

/** Whether the number is a real one, for the field's own message. */
export function isValidPhone(value: string, country: string | null): boolean {
  const text = phoneDigits(value)
  if (text === '') return false
  const parsed = parse(text, (country ?? undefined) as CountryCode | undefined)
  return parsed !== undefined && parsed.isValid()
}

/**
 * The number as it is stored: E.164, or null when there is nothing to store.
 *
 * Validity is required, not hoped for. The parser is generous - "123" with a
 * Russian region parses into `+7123` - and a column full of parseable rubbish
 * is exactly what a length check let through before.
 */
export function toE164(value: string, country: string | null): string | null {
  const text = phoneDigits(value)
  if (text === '') return null
  const parsed = parse(text, (country ?? undefined) as CountryCode | undefined)
  return parsed !== undefined && parsed.isValid() ? parsed.number : null
}

/** Digits only, for a `tel:` link - the one place grouping is wrong. */
export function telHref(value: string): string {
  return phoneDigits(value)
}