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
  /** The API sends it inside the nested account (stage 2.3); it used to be dropped
   *  here, so every list drew a letter while the header showed a photo. */
  avatar_url: string | null
  /** The org-structure position this member holds, as a title (stage 2.5). The
   *  pickers write it under the name, so it travels with the roster instead of
   *  being resolved from ids in every list that needs it. */
  position_title: string | null
}

interface MembershipWithUser extends Membership {
  user: {
    id: string
    email: string
    username: string
    first_name: string | null
    last_name: string | null
    avatar_url: string | null
  } | null
  position_title?: string | null
}

/**
 * The membership row plus the account behind it, as one `Member`.
 *
 * It is a function rather than an inline map because two callers need it - the
 * member list and the org chart, which reads the same people out of the
 * structure snapshot. When it was written twice, the chart's copy silently
 * lacked every field the list had gained (`avatar_url`, stage 2.3).
 */
export function flattenMember(row: MembershipWithUser): Member {
  return {
    user_id: row.user_id,
    role: row.role,
    joined_at: row.joined_at,
    email: row.user?.email ?? '',
    username: row.user?.username ?? '',
    first_name: row.user?.first_name ?? null,
    last_name: row.user?.last_name ?? null,
    avatar_url: row.user?.avatar_url ?? null,
    position_title: row.position_title ?? null,
  }
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
    return rows.map(flattenMember)
  },
  addMember(id: string, email: string, role: OrganizationRole) {
    return api.post<Membership>(`/organizations/${id}/members`, { email, role })
  },
  setMemberRole(id: string, userId: string, role: OrganizationRole) {
    return api.patch<Membership>(`/organizations/${id}/members/${userId}`, { role })
  },
  removeMember(id: string, userId: string) {
    return api.delete<void>(`/organizations/${id}/members/${userId}`)
  },
  update(id: string, body: { name?: string; description?: string | null }) {
    return api.patch<Organization>(`/organizations/${id}`, body)
  },
  delete(id: string) {
    return api.delete<void>(`/organizations/${id}`)
  },
  settings(id: string) {
    return api.get<OrganizationSettings>(`/organizations/${id}/settings`)
  },

  updateSettings(id: string, values: Record<string, unknown>) {
    return api.put<OrganizationSettings>(`/organizations/${id}/settings`, { values })
  },

  // --- organization structure -------------------------------------------

  /** Departments, positions, reporting lines and deputies in one request. */
  structure(id: string) {
    return api.get<OrgStructure>(`/organizations/${id}/structure`)
  },

  createDepartment(
    id: string,
    body: { name: string; description?: string | null; parent_id?: string | null },
  ) {
    return api.post<Department>(`/organizations/${id}/departments`, {
      name: body.name,
      description: body.description ?? null,
      parent_id: body.parent_id ?? null,
    })
  },

  updateDepartment(
    id: string,
    departmentId: string,
    body: {
      name?: string
      description?: string | null
      parent_id?: string | null
      head_id?: string | null
    },
  ) {
    // Spread rather than a fixed shape: `null` on a key means "clear it" and an
    // absent key means "leave it alone", so the two cannot be collapsed.
    return api.patch<Department>(`/organizations/${id}/departments/${departmentId}`, body)
  },

  deleteDepartment(id: string, departmentId: string) {
    return api.delete<void>(`/organizations/${id}/departments/${departmentId}`)
  },

  /** Set the order of one group of siblings - the whole order, not an index. */
  reorderDepartments(id: string, orderedIds: string[]) {
    return api.put<void>(`/organizations/${id}/departments/order`, {
      ordered_ids: orderedIds,
    })
  },

  addDepartmentDeputy(id: string, departmentId: string, deputyId: string) {
    return api.post<void>(`/organizations/${id}/departments/${departmentId}/deputies`, {
      deputy_id: deputyId,
    })
  },

  removeDepartmentDeputy(id: string, departmentId: string, deputyId: string) {
    return api.delete<void>(`/organizations/${id}/departments/${departmentId}/deputies/${deputyId}`)
  },

  createPosition(id: string, body: { title: string; rank?: number | null }) {
    return api.post<OrgPosition>(`/organizations/${id}/positions`, {
      title: body.title,
      department_id: null,
      rank: body.rank ?? null,
    })
  },

  updatePosition(
    id: string,
    positionId: string,
    body: { title?: string; rank?: number | null; department_id?: string | null },
  ) {
    return api.patch<OrgPosition>(`/organizations/${id}/positions/${positionId}`, body)
  },

  deletePosition(id: string, positionId: string) {
    return api.delete<void>(`/organizations/${id}/positions/${positionId}`)
  },

  /** Where one person sits. Only the keys present are changed. */
  placeMember(
    id: string,
    userId: string,
    body: { department_id?: string | null; position_id?: string | null; manager_id?: string | null },
  ) {
    return api.patch<Placement>(
      `/organizations/${id}/members/${userId}/placement`,
      body,
    )
  },

  addDeputy(id: string, userId: string, deputyId: string) {
    return api.post<void>(`/organizations/${id}/members/${userId}/deputies`, {
      deputy_id: deputyId,
    })
  },

  removeDeputy(id: string, userId: string, deputyId: string) {
    return api.delete<void>(`/organizations/${id}/members/${userId}/deputies/${deputyId}`)
  },
}

// --- organization structure types ----------------------------------------

export interface Department {
  id: string
  organization_id: string
  name: string
  description: string | null
  parent_id: string | null
  head_id: string | null
  position: number
}

export interface OrgPosition {
  id: string
  organization_id: string
  title: string
  description: string | null
  department_id: string | null
  rank: number | null
}

/** One person's place in the chart, already resolved. */
export interface Placement {
  user_id: string
  department_id: string | null
  position_id: string | null
  manager_id: string | null
  deputies: string[]
}

/**
 * The whole chart in one payload.
 *
 * `placements` is keyed by user id and covers every member, including those with
 * nothing recorded - the client should not have to guess which are missing.
 */
export interface OrgStructure {
  departments: Department[]
  positions: OrgPosition[]
  members: MembershipWithUser[]
  placements: Record<string, Placement>
  /** Department id -> the people who act for that unit while its head is away.
   * A map rather than a field on `Department` because the relation is
   * many-to-many: two deputies while they are out, one person acting for
   * several units. */
  department_deputies: Record<string, string[]>
}
