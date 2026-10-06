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
    return api.get<SessionUser>('/auth/me')
  },
}
