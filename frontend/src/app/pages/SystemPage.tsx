import { useEffect, useState } from 'react'

import { api } from '../../core/api/client'

interface SystemInfo {
  name: string
  version: string
  environment: string
  api_prefix: string
  modules: Array<{ id: string; name: string; version: string; state: string }>
  permissions: string[]
}

const LOAD_FAILED = 'Backend is unreachable. Start it with `docker compose up -d`.'

export function SystemPage() {
  const [info, setInfo] = useState<SystemInfo | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<SystemInfo>('/system')
      .then(setInfo)
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : LOAD_FAILED))
  }, [])

  if (error) return <p role="alert">{error}</p>
  if (!info) return <p>Loading...</p>

  return (
    <section>
      <h1>Platform</h1>
      <dl>
        <dt>Name</dt>
        <dd>{info.name}</dd>
        <dt>Version</dt>
        <dd>{info.version}</dd>
        <dt>Environment</dt>
        <dd>{info.environment}</dd>
      </dl>

      <h2>Modules</h2>
      <ul>
        {info.modules.map((module) => (
          <li key={module.id}>
            {module.name} ({module.id}) — {module.state}
          </li>
        ))}
      </ul>

      <h2>Permissions</h2>
      <ul>
        {info.permissions.map((permission) => (
          <li key={permission}>{permission}</li>
        ))}
      </ul>
    </section>
  )
}