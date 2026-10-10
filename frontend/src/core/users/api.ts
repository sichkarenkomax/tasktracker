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

/** One phone number, with the note its owner wrote beside it (stage 2.8). */
export interface Phone {
  id: string
  number: string
  comment: string | null
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
  role: string | null
  birthday: string | null
  phones: Phone[]
  contacts_visible: boolean
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
   * An administrator changes somebody's address (stage 2.7).
   *
   * A member of the organization cannot change their own address here - the
   * server refuses it, and the button that offers it is only drawn for somebody
   * the viewer may actually manage.
   */
  setMemberEmail(userId: string, organizationId: string, email: string) {
    return api.patch<PortalUser>(`/users/${userId}/email${buildQuery({ organization_id: organizationId })}`, {
      email,
    })
  },

  /** Own contacts (stage 2.8). */
  setBirthday(birthday: string | null) {
    return api.patch<{ birthday: string | null }>('/users/me/birthday', { birthday })
  },
  phones() {
    return api.get<Phone[]>('/users/me/phones')
  },
  addPhone(input: { number: string; comment: string | null }) {
    return api.post<Phone>('/users/me/phones', input)
  },
  updatePhone(phoneId: string, input: { number: string; comment: string | null }) {
    return api.patch<Phone>(`/users/me/phones/${phoneId}`, input)
  },
  deletePhone(phoneId: string) {
    return api.delete<void>(`/users/me/phones/${phoneId}`)
  },
}
