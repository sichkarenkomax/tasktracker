import { useAuth } from '../auth/AuthContext'
import { organizationsApi } from '../organizations/api'
import { useAsync } from '../hooks/useAsync'
import type { OrganizationRole } from '../organizations/api'

/**
 * What the current user may do in the selected organization.
 *
 * This mirrors the backend matrix (section 25) so the UI can hide affordances a
 * request would be refused for. It is a convenience, never the authority: the API
 * re-checks every request, and a role added to the backend without updating this
 * file shows too little rather than too much.
 */
export interface Capabilities {
  role: OrganizationRole | null
  canCreateTask: boolean
  canEditTask: boolean
  canComment: boolean
  canDeleteTask: boolean
  /**
   * May redraw the organization chart.
   *
   * Mirrors `orgstructure.manage`, which admins and the owner hold by default.
   * Reading the chart is not one of these: everybody may look at it.
   */
  canEditOrgStructure: boolean
}

const VIEWER: Capabilities = {
  role: 'viewer',
  canCreateTask: false,
  canEditTask: false,
  canComment: false,
  canDeleteTask: false,
  canEditOrgStructure: false,
}

const MEMBER: Capabilities = {
  ...VIEWER,
  role: 'member',
  canCreateTask: true,
  canEditTask: true,
  canComment: true,
}

const ADMIN: Capabilities = {
  ...MEMBER,
  role: 'admin',
  canDeleteTask: true,
  canEditOrgStructure: true,
}

const OWNER: Capabilities = { ...ADMIN, role: 'owner' }

const BY_ROLE: Record<OrganizationRole, Capabilities> = {
  viewer: VIEWER,
  member: MEMBER,
  admin: ADMIN,
  owner: OWNER,
}

/**
 * Resolve the caller's capabilities, or the safest set while they are unknown.
 *
 * `OWNER` is the *most* permissive set and `VIEWER` the least, so falling back to
 * `VIEWER` is the direction that fails closed: a briefly hidden button reappears
 * once the membership arrives, whereas a wrongly shown one only produces a 403.
 */
export function useCapabilities(organizationId: string | null): Capabilities {
  const { user, status } = useAuth()
  const memberships = useAsync(
    () =>
      organizationId && status === 'authenticated'
        ? organizationsApi.members(organizationId)
        : Promise.resolve([]),
    [organizationId, status],
  )

  if (!user || !organizationId) return VIEWER
  const own = memberships.data?.find((member) => member.user_id === user.id)
  if (!own) return VIEWER
  return BY_ROLE[own.role] ?? VIEWER
}
