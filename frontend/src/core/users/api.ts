import { api, buildQuery } from '../api/client'
import type { OrganizationRole } from '../organizations/api'
import type { PhoneKind } from './phoneMask'

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

/**
 * One phone number, with its country and what it is for (stage 2.8).
 *
 * `number` is E.164 - the digits with a leading plus - so the column is
 * comparable and sortable, and `country` is what the number is *read* in: a
 * national format is unreadable without it. A null country means it was stored
 * before it was recorded, and it is shown in the international form rather than
 * guessed into somebody's.
 */
export interface Phone {
  id: string
  number: string
  kind: PhoneKind
  country: string | null
}

/**
 * One row of the merged people list (stage 2.17).
 *
 * `in_organization` is what tells a member from an account that is merely
 * registered here, and `email` is null whenever the viewer may not read that
 * person's contacts (stage 2.6) - read `contacts_visible` rather than assuming
 * an empty cell means "no contacts".
 */
export interface Person {
  id: string
  username: string
  first_name: string | null
  last_name: string | null
  avatar_url: string | null
  email: string | null
  status: string
  last_login_at: string | null
  created_at: string
  birthday: string | null
  contacts_visible: boolean
  in_organization: boolean
  role: OrganizationRole | null
  joined_at: string | null
  department_id: string | null
  department_name: string | null
  position_id: string | null
  position_title: string | null
}

export interface PersonPage {
  items: Person[]
  total: number
  limit: number
  offset: number
}

/** What the table is filtered and ordered by (stage 2.17). */
export interface PeopleQuery {
  search?: string
  role?: OrganizationRole
  department_id?: string
  position_id?: string
  status?: 'active' | 'invited' | 'disabled'
  scope?: 'members' | 'outside' | 'all'
  sort?: 'name' | 'email' | 'role' | 'department' | 'position' | 'status' | 'created_at' | 'last_login_at'
  direction?: 'asc' | 'desc'
  limit?: number
  offset?: number
}

/**
 * A colleague's profile (stage 2.6).
 *
 * `email`, `birthday` and `phones` are nullable because the server may withhold
 * them: read `contacts_visible` to tell "hidden from you" apart from "not
 * filled in", and never treat an empty list as proof that somebody has no phone.
 */
export interface MemberProfile {
  id: string
  email: string | null
  username: string
  first_name: string | null
  last_name: string | null
  avatar_url: string | null
  last_login_at: string | null
  department_id: string | null
  department_name: string | null
position_id: string | null
  position_title: string | null
  manager_id: string | null
  role: string | null
  birthday: string | null
  phones: Phone[]
  contacts_visible: boolean
  /** The account's own state; a locked login is locked in every organization. */
  status: string
  /** False until chat arrives in stage 8; the screen says so rather than
   *  offering a button that cannot do anything. */
  can_message: boolean
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

  /**
   * A colleague's profile (stage 2.6).
   *
   * One route for two audiences: the name, department, position and avatar are
   * always in the answer, and whether the contacts are filled in is the server's
   * decision, per request. `contacts_visible` is therefore part of the contract
   * rather than something the client infers from empty fields - "withheld" and
   * "none set" are different things and the screen has to say which it is.
   */
  profile(userId: string, organizationId: string) {
    return api.get<MemberProfile>(`/users/${userId}/profile${buildQuery({ organization_id: organizationId })}`)
  },

  /**
   * The merged people list (stage 2.17).
   *
   * One call rather than two: the organization's members and - for a superuser -
   * the accounts of this installation that are not in it come back in the same
   * page, sorted and filtered by the server. Merging them in the browser would
   * mean two pagination cursors to keep in step and an order that only holds
   * for the rows that happened to be on screen.
   */
  people(organizationId: string, query: PeopleQuery = {}) {
    return api.get<PersonPage>(
      `/organizations/${organizationId}/people${buildQuery({ ...query })}`,
    )
  },

  /**
   * An administrator changes somebody's profile (stage 2.18).
   *
   * One route for name, address, birthday, role, placement and status, because
   * a form that saves half of what was typed is worse than a refusal. The keys
   * left out are left alone; `birthday: null` removes the date.
   */
  updateMember(
    userId: string,
    organizationId: string,
    changes: {
      first_name?: string
      last_name?: string
      email?: string
      birthday?: string | null
      status?: 'active' | 'invited' | 'disabled'
      role?: OrganizationRole
      department_id?: string | null
      position_id?: string | null
      manager_id?: string | null
      /** Somebody's whole set of numbers, as the administrator sees it (2.18).
       *  Omitted means "leave the numbers alone"; a list means "these are theirs",
       *  so a number not in the list is removed. */
      phones?: Array<{ number: string; kind: PhoneKind; country: string | null }>
    },
  ) {
    return api.patch<PortalUser>(`/users/${userId}${buildQuery({ organization_id: organizationId })}`, changes)
  },

  /**
   * An administrator changes somebody's address (stage 2.7).
   *
   * A member of the organization cannot change their own address here - the
   * server refuses it, and the button that offers it is only drawn for somebody
   * the viewer may actually manage.
   */
  setMemberEmail(userId: string, organizationId: string, email: string) {
    return api.patch<PortalUser>(
      `/users/${userId}/email${buildQuery({ organization_id: organizationId })}`,
      { email },
    )
  },

  /** Own contacts (stage 2.8). */
  setBirthday(birthday: string | null) {
    return api.patch<{ birthday: string | null }>('/users/me/birthday', { birthday })
  },
  phones() {
    return api.get<Phone[]>('/users/me/phones')
  },
  addPhone(input: { number: string; kind: PhoneKind; country: string | null }) {
    return api.post<Phone>('/users/me/phones', input)
  },
  updatePhone(phoneId: string, input: { number: string; kind: PhoneKind; country: string | null }) {
    return api.patch<Phone>(`/users/me/phones/${phoneId}`, input)
  },
  deletePhone(phoneId: string) {
    return api.delete<void>(`/users/me/phones/${phoneId}`)
  },
}
