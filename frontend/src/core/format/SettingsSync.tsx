import { useEffect } from 'react'

import { setDateFormat } from '../format'
import { useAsync } from '../hooks/useAsync'
import { organizationsApi } from '../organizations/api'
import { useOrganization } from '../organizations/OrganizationContext'
import { personalSettingsApi } from '../settings/api'
import { setPeopleInfo } from '../settings/peopleInfo'

/**
 * Keeps the personal display settings in step with the server.
 *
 * Two sources, and the order matters: a person's own format outranks the portal's,
 * which is the precedence the storage quotas use too. Neither is read from the
 * browser, because these settings do not have to be in hand before the first
 * paint - the language and the theme are (see `I18nProvider` and `theme.ts`), and
 * a date or a person is something that can arrive a moment later without a flash
 * of the wrong thing.
 *
 * One component for both keys on purpose: the answer arrives in one request, and
 * two synchronisers would either read the same personal settings twice or drift
 * apart about when they had read them.
 *
 * Renders nothing: it is a synchroniser, and the values it sets are what
 * `formatDate` and `getPeopleInfo` read wherever they are used.
 */
export function SettingsSync() {
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

    // The other personal key, and personal-only by decision (2.5): there is no
    // portal-side variant to fall back to. Absent means the reader never chose,
    // and `setPeopleInfo` puts the default back.
    setPeopleInfo(personal.data?.stored?.people_info)
  }, [settings.data, personal.data])

  return null
}