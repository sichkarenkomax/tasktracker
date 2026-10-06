import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { en } from './en'
import type { TranslationKey } from './en'
import { ru } from './ru'
import type { Locale } from './ru'

/**
 * Translations.
 *
 * Deliberately hand-rolled: the whole product is a dozen screens and two
 * languages, and a translation library would add a build dependency, a bundler
 * plugin and a second thing to learn for less code than this directory.
 *
 * The dictionaries are plain objects and `ru` is typed against `en`, so a missing
 * translation is a compile error rather than a `undefined` on a screen.
 */

export const DICTIONARIES: Record<Locale, Record<TranslationKey, string>> = { en, ru }

export const LOCALES: ReadonlyArray<{ id: Locale; label: string }> = [
  { id: 'en', label: 'English' },
  { id: 'ru', label: 'Русский' },
]

const STORAGE_KEY = 'tasktracker.locale'

export type TranslateParams = Record<string, string | number>

export type Translate = (key: TranslationKey, params?: TranslateParams) => string

interface I18nState {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: Translate
}

const I18nContext = createContext<I18nState | null>(null)

/** `{name}` placeholders. A missing value is left as-is rather than printed as
 *  `undefined`, so a missing parameter is visible but not fatal. */
function interpolate(template: string, params?: TranslateParams): string {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = params[name]
    return value === undefined ? match : String(value)
  })
}

function detectLocale(): Locale {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored === 'en' || stored === 'ru') return stored
  } catch {
    // Locked-down profiles refuse localStorage; fall through to the browser.
  }
  // A Russian browser should not have to find the switcher first.
  return navigator.language.toLowerCase().startsWith('ru') ? 'ru' : 'en'
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(detectLocale)

  useEffect(() => {
    // Kept in sync so a reload does not bounce a Russian reader back to English.
    document.documentElement.lang = locale
    try {
      window.localStorage.setItem(STORAGE_KEY, locale)
    } catch {
      /* preference only */
    }
  }, [locale])

  const setLocale = useCallback((next: Locale) => setLocaleState(next), [])

  const t = useCallback<Translate>(
    (key, params) => interpolate(DICTIONARIES[locale][key] ?? en[key], params),
    [locale],
  )

  const value = useMemo<I18nState>(() => ({ locale, setLocale, t }), [locale, setLocale, t])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18nState {
  const context = useContext(I18nContext)
  if (context === null) {
    throw new Error('useI18n must be used inside <I18nProvider>')
  }
  return context
}

/** The locale as a BCP-47 tag, for `Intl` and `<html lang>`. */
export function useLocale(): string {
  return useI18n().locale
}

export type { Locale, TranslationKey }
