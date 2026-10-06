import { api, buildQuery } from '../api/client'

export interface Project {
  id: string
  organization_id: string
  name: string
  description: string | null
  status: 'planned' | 'active' | 'paused' | 'completed' | 'cancelled'
  owner_id: string
  created_at: string
  updated_at: string
}

export const projectsApi = {
  list(organizationId: string) {
    return api.get<Project[]>(`/projects${buildQuery({ organization_id: organizationId })}`)
  },
  create(organizationId: string, name: string, description?: string) {
    return api.post<Project>('/projects', {
      organization_id: organizationId,
      name,
      description: description ?? null,
    })
  },
  get(projectId: string, organizationId: string) {
    return api.get<Project>(`/projects/${projectId}${buildQuery({ organization_id: organizationId })}`)
  },
  update(projectId: string, organizationId: string, body: { name?: string; description?: string }) {
    return api.patch<Project>(
      `/projects/${projectId}${buildQuery({ organization_id: organizationId })}`,
      body,
    )
  },
}
