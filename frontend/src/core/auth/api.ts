/** Auth endpoints. The session cookie is set by the API; nothing is stored here. */
import { api } from '../api/client'
import type { SessionUser, TokenResponse } from './types'

export const authApi = {
  register(input: {
    email: string
    username: string
    password: string
    first_name?: string
    last_name?: string
  }) {
    return api.post<TokenResponse>('/auth/register', input)
  },

  /** `login` accepts either an email address or a username. */
  login(input: { login: string; password: string }) {
    return api.post<TokenResponse>('/auth/login', input)
  },

  logout() {
    return api.post<void>('/auth/logout')
  },

  changePassword(body: { current_password: string; new_password: string }) {
    return api.post<void>('/auth/change-password', body)
  },

  me() {
    // `/users/me` rather than `/auth/me`: only the former carries `is_superuser`,
    // and the whole menu branches on that flag.
    return api.get<SessionUser>('/users/me')
  },

  updateProfile(body: {
    first_name?: string
    last_name?: string
    /** A file id from the files API, never a URL (stage 2.3). */
    avatar_file_id?: string | null
  }) {
    return api.patch<SessionUser>('/users/me', body)
  },
}
