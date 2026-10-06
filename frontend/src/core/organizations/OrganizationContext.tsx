import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { useAuth } from '../auth/AuthContext'
import { organizationsApi } from './api'
import type { Organization } from './api'

/**
 * Which organization the whole UI is working in.
 *
 * Almost every request needs an organization id, and it is a *choice* rather
 * than something derivable from the URL: the task routes carry
 * `?organization_id=` for exactly this reason (section 26). Holding the choice
 * once here is what keeps a hundred call sites from each inventing their own.
 */

const STORAGE_KEY = 'tasktracker.organization'

/**
 * Persist the choice.
 *
 * Exported on its own so a caller that has just created an organization can
 * record the intent before the list reloads; the provider picks it up on the
 * next fetch instead of the caller having to set state it does not own.
 */
export function rememberOrganization(id: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, id)
  } catch {
    /* preference only */
  }
}

function readRemembered(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY)
  } catch {
    // Private browsing and locked-down profiles refuse localStorage. A forgotten
    // preference is not a reason to fail, so fall back to the first organization.
    return null
  }
}

interface OrganizationState {
  organizations: Organization[]
  current: Organization | null
  loading: boolean
  error: string | null
  select: (id: string) => void
  reload: () => void
}

const OrganizationContext = createContext<OrganizationState | null>(null)

export function OrganizationProvider({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    // Only ask for organizations once a session exists. This provider is mounted
    // above the login page, so without this guard it would spend its one fetch on
    // a 401 and leave every authenticated page stuck on "Loading" for good.
    if (status !== 'authenticated') {
      setOrganizations([])
      setSelectedId(null)
      setError(null)
      setLoading(false)
      return
    }

    let cancelled = false
    setLoading(true)
    organizationsApi
      .list()
      .then((items) => {
        if (cancelled) return
        setOrganizations(items)
        setError(null)
        setSelectedId((previous) => {
          const stillValid = previous && items.some((item) => item.id === previous)
          // A remembered id that no longer exists (removed on another device)
          // would otherwise leave the UI with no organization at all.
          return stillValid ? previous : (readRemembered() ?? items[0]?.id ?? null)
        })
      })
      .catch((cause: unknown) => {
        if (cancelled) return
        setError(cause instanceof Error ? cause.message : 'Cannot load organizations')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [nonce, status])

  const select = useCallback((id: string) => {
    rememberOrganization(id)
    setSelectedId(id)
  }, [])

  const reload = useCallback(() => setNonce((value) => value + 1), [])

  const value = useMemo<OrganizationState>(() => {
    const current = organizations.find((item) => item.id === selectedId) ?? null
    return { organizations, current, loading, error, select, reload }
  }, [organizations, selectedId, loading, error, select, reload])

  return <OrganizationContext.Provider value={value}>{children}</OrganizationContext.Provider>
}

export function useOrganization(): OrganizationState {
  const context = useContext(OrganizationContext)
  if (context === null) {
    throw new Error('useOrganization must be used inside <OrganizationProvider>')
  }
  return context
}

/**
 * The selected organization id, or null while it is still being resolved.
 *
 * Pages take this rather than the whole object so that a missing organization is
 * something they have to handle, instead of a null dereference three components
 * deep.
 */
export function useOrganizationId(): string | null {
  return useOrganization().current?.id ?? null
}
