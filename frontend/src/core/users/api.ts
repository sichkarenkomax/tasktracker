import { api, buildQuery } from '../api/client'

/**
 * The portal administrator's view of every account on this installation.
 *
 * Distinct from an organization's member list on purpose: this one crosses
 * tenants, so it exists only behind `is_superuser` and is a different screen.
 */
export interface PortalUser {
  id: string
  email: string
  username: string
  first_name: string | null
  last_name: string | null
  avatar_url: string | null
  status: string
  created_at: string
  is_superuser: boolean
  last_login_at: string | null
}

export interface PortalUserPage {
  items: PortalUser[]
  total: number
  limit: number
  offset: number
}

export const usersApi = {
  list(options: { search?: string; limit?: number; offset?: number } = {}) {
    return api.get<PortalUserPage>(
      `/users${buildQuery({ search: options.search, limit: options.limit, offset: options.offset })}`,
    )
  },
  setSuperuser(userId: string, isSuperuser: boolean) {
    return api.patch<PortalUser>(`/users/${userId}/superuser`, { is_superuser: isSuperuser })
  },
}
