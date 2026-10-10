/** Session types shared by the auth layer and everything that renders a user. */
export interface SessionUser {
  id: string
  email: string
  username: string
  first_name: string | null
  last_name: string | null
  avatar_url: string | null
  status: string
  created_at: string
  /**
   * Portal administrator, as opposed to an administrator of one organization.
   *
   * Kept on the session because the whole UI branches on it: the user list appears
   * in the menu only for these people, and the server refuses it for everybody
   * else regardless.
   */
  is_superuser: boolean
  last_login_at: string | null
  /** The person's own birthday (stage 2.8). On the session because the profile
   *  screen reads it from the signed-in person, like the name above. */
  birthday?: string | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_at: string
  user: SessionUser
}

/** What a person is called in the UI. Falls back through the fields we have. */
export function displayName(user: Pick<SessionUser, 'first_name' | 'last_name' | 'username'>): string {
  const full = [user.first_name, user.last_name].filter(Boolean).join(' ').trim()
  return full || user.username
}
