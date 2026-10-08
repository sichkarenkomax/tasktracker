import { useEffect } from 'react'

import { setDateFormat } from '../format'
import { useAsync } from '../hooks/useAsync'
import { organizationsApi } from '../organizations/api'
import { useOrganization } from '../organizations/OrganizationContext'
import { personalSettingsApi } from '../settings/api'

/**
 * Keeps the date format in step with the settings.
 *
 * Two sources, and the order matters: a person's own format outranks the portal's,
 * which is the precedence the storage quotas use too. Neither is read from the
 * browser, because this setting does not have to be in hand before the first
 * paint - the language and the theme are (see `I18nProvider` and `theme.ts`), and
 * a date is text that can arrive a moment later without a flash of the wrong year.
 *
 * Renders nothing: it is a synchroniser, and the value it sets is what
 * `formatDate` reads wherever a date is written.
 */
export function DateFormatSync() {
  const { current } = useOrganization()
  const organizationId = current?.id ?? null

  const settings = useAsync(
    () => (organizationId ? organizationsApi.settings(organizationId) : Promise.resolve(null)),
    [organizationId],
  )

  const personal = useAsync(
    () => (organizationId ? personalSettingsApi.read(organizationId) : Promise.resolve(null)),
    [organizationId],
  )

  useEffect(() => {
    // Only a format the person actually stored counts as their opinion. The
    // merged `values` answer includes the registry default, and treating that as
    // a choice would pin everybody to the default and leave the portal's own
    // setting unreachable - the fallback would be dead on arrival.
    const own = personal.data?.stored?.date_format
    if (typeof own === 'string') setDateFormat(own)
    const portal = settings.data?.values?.date_format
    if (typeof portal === 'string' && typeof own !== 'string') setDateFormat(portal)
  }, [settings.data, personal.data])

  return null
}