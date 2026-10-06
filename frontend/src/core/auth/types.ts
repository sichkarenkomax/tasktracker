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
