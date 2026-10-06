import { api } from '../api/client'

export interface Organization {
  id: string
  name: string
  slug: string
  description: string | null
  created_at: string
  updated_at: string
}

export type OrganizationRole = 'owner' | 'admin' | 'member' | 'viewer'

export interface Membership {
  user_id: string
  role: OrganizationRole
  joined_at: string | null
}

export interface OrganizationSettings {
  values: Record<string, unknown>
  updated_at: string | null
}

/**
 * A member as the UI needs them: the membership row plus the account behind it,
 * flattened. The API nests the account under `user` and marks it optional, so
 * this is where that flattening is decided once instead of in every picker.
 */
export interface Member extends Membership {
  email: string
  username: string
  first_name: string | null
  last_name: string | null
}

interface MembershipWithUser extends Membership {
  user: {
    id: string
    email: string
    username: string
    first_name: string | null
    last_name: string | null
  } | null
}

export const organizationsApi = {
  list() {
    return api.get<Organization[]>('/organizations')
  },
  create(name: string) {
    return api.post<Organization>('/organizations', { name })
  },
  get(id: string) {
    return api.get<Organization>(`/organizations/${id}`)
  },
  async members(id: string): Promise<Member[]> {
    const rows = await api.get<MembershipWithUser[]>(`/organizations/${id}/members`)
    return rows.map((row) => ({
      user_id: row.user_id,
      role: row.role,
      joined_at: row.joined_at,
      email: row.user?.email ?? '',
      username: row.user?.username ?? '',
      first_name: row.user?.first_name ?? null,
      last_name: row.user?.last_name ?? null,
    }))
  },
  settings(id: string) {
    return api.get<OrganizationSettings>(`/organizations/${id}/settings`)
  },
}
