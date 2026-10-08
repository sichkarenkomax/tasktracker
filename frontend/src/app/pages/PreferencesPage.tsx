import { useState } from 'react'
import { Link } from 'react-router-dom'

import { useI18n, LOCALES } from '../../core/i18n'
import type { Locale } from '../../core/i18n'
import { getTheme, setTheme } from '../../core/theme/theme'
import type { Theme } from '../../core/theme/theme'
import { Listbox } from '../../core/ui/Listbox'

/**
 * Personal settings (stage 2.1).
 *
 * The screen is about one person's preferences and nothing else: what they read
 * the portal in and what it looks like. Account facts (name, email, password,
 * session) stay in the profile - a password is not a preference, and looking for
 * one under "settings" is how people end up in an administrator's menu.
 *
 * Where the values live is a separate question from what the screen offers. Both
 * settings here are still read from the browser (stage 1.1: the first paint must
 * not wait on a round trip, and a preference nobody else can see has no reason on
 * a server yet), while `user_settings` and its key registry already exist for the
 * keys that *do* need to be per person. So the vocabulary of this screen is
 * declared in one place, and moving a key to the server is changing where it is
 * read - not what is on the screen.
 */
export function PreferencesPage() {
  const { t, locale, setLocale } = useI18n()
  const [theme, chooseTheme] = useState<Theme>(getTheme)

  return (
    <section className="narrow">
      <h1>{t('preferences.title')}</h1>
      <p className="muted">{t('preferences.subtitle')}</p>

      <section className="panel">
        <h2>{t('app.language')}</h2>
        <label className="field">
          <span className="visually-hidden">{t('app.language')}</span>
          <Listbox<Locale>
            value={locale}
            options={LOCALES.map((entry) => ({ value: entry.id, label: entry.label }))}
            onChange={(next) => {
              if (next !== null) setLocale(next)
            }}
          />
        </label>
      </section>

      <section className="panel">
        <h2>{t('settings.theme')}</h2>
        <label className="field">
          <span className="visually-hidden">{t('settings.theme')}</span>
          <Listbox<Theme>
            value={theme}
            options={[
              { value: 'gold', label: t('settings.themeGold') },
              { value: 'blue', label: t('settings.themeBlue') },
            ]}
            onChange={(next) => {
              if (next === null) return
              chooseTheme(next)
              setTheme(next)
            }}
          />
        </label>
      </section>

      <section className="panel">
        <h2>{t('preferences.account')}</h2>
        <p className="muted">{t('preferences.accountHint')}</p>
        <Link className="button" to="/users/me">
          {t('nav.profile')}
        </Link>
      </section>
    </section>
  )
}