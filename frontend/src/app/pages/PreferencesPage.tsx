import { useState } from 'react'
import { Link } from 'react-router-dom'

import { DATE_FORMATS, getDateFormat, setDateFormat } from '../../core/format'
import { useAsync, useMutation } from '../../core/hooks/useAsync'
import { useI18n, LOCALES } from '../../core/i18n'
import type { Locale } from '../../core/i18n'
import { useOrganization } from '../../core/organizations/OrganizationContext'
import { personalSettingsApi } from '../../core/settings/api'
import { getTheme, setTheme } from '../../core/theme/theme'
import type { Theme } from '../../core/theme/theme'
import { Listbox } from '../../core/ui/Listbox'
import type { TranslationKey } from '../../core/i18n'

/**
 * Personal settings (stage 2.1).
 *
 * The screen is about one person's preferences and nothing else: what they read
 * the portal in, what it looks like, and how dates are written. Account facts
 * (name, email, password, session) stay in the profile - a password is not a
 * preference, and looking for one under "settings" is how people end up in an
 * administrator's menu.
 *
 * Where each value lives is a separate question from what the screen offers. The
 * language and the theme are still read from the browser (stage 1.1: the first
 * paint must not wait on a round trip, and nobody else can see them anyway). The
 * date format is stored per person, because it changes every date on every screen
 * and a person in a portal that writes `08.10.2026` may still want `2026-10-08`.
 * A personal value outranks the portal's, the same precedence the storage quotas
 * use.
 */
/** The portal's choice, spelled as a setting value of its own. */
const FOLLOW_PORTAL = 'portal' as const

export function PreferencesPage() {
  const { t, locale, setLocale } = useI18n()
  const { current } = useOrganization()
  const organizationId = current?.id ?? null

  const [theme, chooseTheme] = useState<Theme>(getTheme)
  const [dateFormat, setFormat] = useState<string>(getDateFormat())

  const personal = useAsync(
    () => (organizationId ? personalSettingsApi.read(organizationId) : Promise.resolve(null)),
    [organizationId],
  )

  const saveDateFormat = useMutation<{ date_format: string | null }, void>(async (body) => {
    if (!organizationId) return
    await personalSettingsApi.update(organizationId, body)
  })

  const formats: Array<{ value: string; label: string }> = [
    // First, and deliberately: choosing a format once must not be a life
    // sentence. This row writes `null`, which removes the personal override and
    // lets the portal's own format show through again.
    { value: FOLLOW_PORTAL, label: t('settings.dateFormatPortal') },
    ...DATE_FORMATS.map((id) => ({ value: id, label: t(`dateFormat.${id}` as TranslationKey) })),
  ]

  const storedFormat = personal.data?.stored?.date_format as string | undefined

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
        <h2>{t('settings.dateFormat')}</h2>
        <p className="muted">{t('settings.dateFormatHint')}</p>
        <label className="field">
          <span className="visually-hidden">{t('settings.dateFormat')}</span>
<Listbox<string>
              value={dateFormat}
              options={formats}
              onChange={(next) => {
                if (next === null) return
                setFormat(next)
                // Applied at once: a date format is text, and waiting for a save
                // button to make the numbers change would only be confusing. The
                // server is told afterwards, and a failure says so below.
                if (next === FOLLOW_PORTAL) {
                  // Clearing the override leaves the module holding the portal's
                  // format, which the reader can see by looking at the screen.
                  setDateFormat(personal.data?.values?.date_format as string | undefined)
                } else {
                  setDateFormat(next)
                }
                if (storedFormat !== next) {
                  void saveDateFormat.run({ date_format: next === FOLLOW_PORTAL ? null : next })
                }
              }}
            />
        </label>
        {saveDateFormat.error ? (
          <p className="notice notice--error" role="alert">
            {saveDateFormat.error}
          </p>
        ) : null}
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