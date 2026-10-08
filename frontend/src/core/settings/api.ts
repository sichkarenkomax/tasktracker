import { api, buildQuery } from '../api/client'

/**
 * The caller's own settings (stage 2.1).
 *
 * The portal's settings come from `organizationsApi.settings`; these are the
 * person-level ones, and where the two name the same key the person's value is
 * the one that applies - the same precedence storage quotas use.
 */

export interface SettingDefinition {
  type: string
  default: unknown
  values?: string[]
}

export interface PersonalSettings {
  organization_id: string
  values: Record<string, unknown>
  /** Only the keys this person actually stored - no defaults merged in. */
  stored: Record<string, unknown>
  available: Record<string, SettingDefinition>
}

export const personalSettingsApi = {
  read(organizationId: string) {
    return api.get<PersonalSettings>(`/users/me/settings${buildQuery({ organization_id: organizationId })}`)
  },

  update(organizationId: string, values: Record<string, unknown>) {
    return api.put<PersonalSettings>(`/users/me/settings${buildQuery({ organization_id: organizationId })}`, {
      values,
    })
  },
}