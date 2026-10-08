import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'

import { tasksApi } from './api'

/**
 * How many open tasks are past their deadline, for the rail's red label.
 *
 * One query with `limit=1` and the answer taken from `total`: the list endpoint
 * already counts exactly what the filter selects, and counting in the browser
 * would mean fetching every overdue task on every page to add up numbers that the
 * server had in hand.
 *
 * It refreshes when the route changes, when the window regains focus and once a
 * minute. That last one is a compromise - a person who leaves a task sitting past
 * its deadline in another tab would otherwise see a stale label until they
 * navigated somewhere - and it stops while the tab is hidden, because a poll in a
 * background tab is traffic nobody is waiting for.
 */
export function useOverdueCount(organizationId: string | null): number {
  const [count, setCount] = useState(0)
  const { pathname } = useLocation()

  const refresh = useCallback(async () => {
    if (!organizationId) {
      setCount(0)
      return
    }
    try {
      const page = await tasksApi.list(organizationId, { overdue: true, limit: 1 })
      setCount(page.total)
    } catch {
      // A badge is not worth an error banner: leaving the last known number up
      // is better than showing nothing, and the tasks list itself is the truth.
      setCount((previous) => previous)
    }
  }, [organizationId])

  useEffect(() => {
    void refresh()
  }, [refresh, pathname])

  useEffect(() => {
    const onFocus = () => void refresh()
    window.addEventListener('focus', onFocus)
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh()
    }, 60_000)
    return () => {
      window.removeEventListener('focus', onFocus)
      window.clearInterval(timer)
    }
  }, [refresh])

  return count
}