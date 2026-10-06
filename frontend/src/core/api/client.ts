/**
 * The one place that knows how to talk to the API.
 *
 * Two rules live here and nowhere else:
 *
 * * the versioned prefix (/api/v1) is never spelled out by a caller;
 * * a session travels in the httpOnly cookie the API sets, so no token is ever
 *   kept in JavaScript where a single XSS could read it (section 44). The
 *   `Authorization` header stays supported for scripts and tests.
 *
 * Errors arrive as `{ "error": { "code", "message" } }`, so `ApiError.code` is
 * the stable thing to branch on - never the human-readable message.
 */
export const API_PREFIX = '/api/v1'

/** Domain error codes the backend can return (see app/core/errors.py). */
export type ApiErrorCode =
  | 'authentication_error'
  | 'permission_denied'
  | 'not_found'
  | 'conflict'
  | 'validation_error'
  | 'invalid_credentials'
  | 'rate_limited'
  | 'internal_error'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: ApiErrorCode | 'unknown',
    readonly detail: string,
    readonly details?: Record<string, unknown>,
  ) {
    super(detail)
    this.name = 'ApiError'
  }

  /** True when the caller has to sign in again (or was never signed in). */
  get isUnauthorized(): boolean {
    return this.status === 401
  }

  /** True when the record is gone, or was never visible to this user. */
  get isNotFound(): boolean {
    return this.status === 404
  }

  /** True when the request itself was malformed - the client's own bug. */
  get isValidation(): boolean {
    return this.status === 422
  }
}

export type QueryValue = string | number | boolean | null | undefined | readonly string[]

export type Query = Record<string, QueryValue>

/**
 * Build a query string, dropping empty values.
 *
 * Repeated filters (`?status=todo&status=done`) are arrays; anything undefined,
 * null or empty string means "not filtering by this", which keeps call sites free
 * of `if (x) params.x = x` noise.
 */
export function buildQuery(query: Query = {}): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) {
      for (const item of value) search.append(key, item)
    } else {
      search.append(key, String(value))
    }
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ''
}

interface ErrorBody {
  error?: {
    code?: string
    message?: string
    details?: Record<string, unknown>
  }
  detail?: unknown
}

/** Turn any failure into something a person can read. */
function describe(payload: unknown, fallback: string): { code: ApiErrorCode | 'unknown'; message: string; details?: Record<string, unknown> } {
  if (typeof payload === 'string' && payload.trim()) {
    return { code: 'unknown', message: payload.trim() }
  }
  if (payload && typeof payload === 'object') {
    const body = payload as ErrorBody
    if (body.error && typeof body.error === 'object') {
      return {
        code: (body.error.code as ApiErrorCode | undefined) ?? 'unknown',
        message: body.error.message ?? fallback,
        details: body.error.details,
      }
    }
    // FastAPI's own validation errors, which arrive as a list of field problems.
    if (body.detail !== undefined) {
      return { code: 'validation_error', message: fallback, details: { detail: body.detail } }
    }
  }
  return { code: 'unknown', message: fallback }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    method,
    // Same-origin requests send cookies by default, but being explicit keeps the
    // client working unchanged behind a proxy that fronts the SPA elsewhere.
    credentials: 'include',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (response.status === 204 || response.status === 205) {
    return undefined as T
  }

  const raw = await response.text()
  let payload: unknown = null
  if (raw) {
    try {
      payload = JSON.parse(raw)
    } catch {
      payload = raw
    }
  }

  if (!response.ok) {
    const { code, message, details } = describe(payload, `Request failed (${response.status})`)
    throw new ApiError(response.status, code, message, details)
  }

  return payload as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
}
