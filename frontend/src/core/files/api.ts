import { api, buildQuery } from '../api/client'

/**
 * The files API (stage 2.2).
 *
 * The first call is the one that matters more than it looks: before anything is
 * uploaded, the client asks what the portal will accept. A limit enforced only
 * when an upload finishes is a limit the person finds out about after waiting for
 * their file to travel, and a quota discovered at that moment looks like the
 * portal's fault rather than a setting they never saw.
 */

export interface UploadLimits {
  max_file_size_bytes: number
  storage_quota_bytes: number
  used_bytes: number
  /** Null means nothing caps this person beyond the per-file limit. */
  remaining_bytes: number | null
  allowed_content_types: string[]
}

export interface StoredFile {
  id: string
  organization_id: string
  owner_id: string
  filename: string
  content_type: string
  size_bytes: number
  created_at: string
}

export interface MyQuota {
  used_bytes: number
  limit_bytes: number | null
  /** Whose limit decided it: `user`, `department` or `none`. */
  quota_source: string
}

export interface StorageQuota {
  id: string
  department_id: string | null
  user_id: string | null
  limit_bytes: number
}

export const filesApi = {
  limits(organizationId: string) {
    return api.get<UploadLimits>(`/files/limits${buildQuery({ organization_id: organizationId })}`)
  },

  myQuota(organizationId: string) {
    return api.get<MyQuota>(`/files/quota/me${buildQuery({ organization_id: organizationId })}`)
  },

  /**
   * Upload one file.
   *
   * `prepareImage` runs first, so what travels is already shrunk - see
   * `prepare.ts` for why the resizing happens here rather than on the server.
   */
  upload(organizationId: string, file: File) {
    const form = new FormData()
    form.append('file', file, file.name)
    return api.upload<StoredFile>(`/files${buildQuery({ organization_id: organizationId })}`, form)
  },

  downloadUrl(fileId: string, organizationId: string): string {
    return `/api/v1/files/${fileId}${buildQuery({ organization_id: organizationId })}`
  },

  remove(fileId: string, organizationId: string) {
    return api.delete<void>(`/files/${fileId}${buildQuery({ organization_id: organizationId })}`)
  },

  quotas(organizationId: string) {
    return api.get<StorageQuota[]>(`/files/quotas${buildQuery({ organization_id: organizationId })}`)
  },

  setQuota(
    organizationId: string,
    payload: { department_id?: string | null; user_id?: string | null; limit_bytes: number },
  ) {
    return api.put<StorageQuota>(
      `/files/quotas${buildQuery({ organization_id: organizationId })}`,
      payload,
    )
  },

  removeQuota(quotaId: string, organizationId: string) {
    return api.delete<void>(
      `/files/quotas/${quotaId}${buildQuery({ organization_id: organizationId })}`,
    )
  },
}