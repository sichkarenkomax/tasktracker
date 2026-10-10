import { useState } from 'react'
import { Link } from 'react-router-dom'

import { DATE_FORMATS, setDateFormat } from '../../core/format'
import { useAsync, useMutation } from '../../core/hooks/useAsync'
import { useI18n, LOCALES } from '../../core/i18n'
import type { Locale } from '../../core/i18n'
import { useOrganization } from '../../core/organizations/OrganizationContext'
import { personalSettingsApi } from '../../core/settings/api'
import { PEOPLE_INFO_DEFAULT, setPeopleInfo } from '../../core/settings/peopleInfo'
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

  const personal = useAsync(
    () => (organizationId ? personalSettingsApi.read(organizationId) : Promise.resolve(null)),
    [organizationId],
  )

  const saveDateFormat = useMutation<{ date_format: string | null }, void>(async (body) => {
    if (!organizationId) return
    await personalSettingsApi.update(organizationId, body)
  })

  const savePeopleInfo = useMutation<{ people_info: string | null }, void>(async (body) => {
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
  const portalFormat = personal.data?.values?.date_format as string | undefined

  // The control shows what is stored, not what the module happened to hold when
  // the screen mounted: a personal format arrives a moment after the first
  // render, so a value captured at mount is the default wearing the stored
  // format's clothes. State holds only the change just made.
  const [dateFormatDraft, setDateFormatDraft] = useState<string | null>(null)
  const dateFormat = dateFormatDraft ?? storedFormat ?? FOLLOW_PORTAL

  // Same arrangement for the people preference (stage 2.5), except that it has no
  // portal-side value to fall back to: the control shows the stored key, and an
  // untouched one reads as the default.
  const storedPeopleInfo = personal.data?.stored?.people_info as string | undefined
  const [peopleInfoDraft, setPeopleInfoDraft] = useState<string | null>(null)

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
                setDateFormatDraft(next)
                // Applied at once: a date format is text, and waiting for a save
                // button to make the numbers change would only be confusing. The
                // server is told afterwards, and a failure says so below.
                setDateFormat(next === FOLLOW_PORTAL ? portalFormat : next)
                void saveDateFormat
                  .run({ date_format: next === FOLLOW_PORTAL ? null : next })
                  .then((done) => {
                    if (done === null) return
                    // Re-read rather than trust what is on screen: the stored value
                    // the control falls back to is the one this very save replaced.
                    setDateFormatDraft(null)
                    personal.reload()
                  })
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
        <h2>{t('settings.peopleInfo')}</h2>
        <p className="muted">{t('settings.peopleInfoHint')}</p>
        <label className="field">
          <span className="visually-hidden">{t('settings.peopleInfo')}</span>
          <Listbox<string>
            value={peopleInfoDraft ?? storedPeopleInfo ?? PEOPLE_INFO_DEFAULT}
            options={[
              { value: 'full', label: t('settings.peopleInfoFull') },
              { value: 'names', label: t('settings.peopleInfoNames') },
            ]}
            onChange={(next) => {
              if (next === null) return
              setPeopleInfoDraft(next)
              // Applied at once, and for the same reason as the format above: the
              // pickers are open in other tabs and behind this screen, and a
              // switch that only takes effect after a save would look broken.
              setPeopleInfo(next)
              void savePeopleInfo.run({ people_info: next }).then((done) => {
                if (done === null) return
                setPeopleInfoDraft(null)
                personal.reload()
              })
            }}
          />
        </label>
        {savePeopleInfo.error ? (
          <p className="notice notice--error" role="alert">
            {savePeopleInfo.error}
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