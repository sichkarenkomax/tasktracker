import type { ReactNode } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { AppShell } from '../core/layout/AppShell'
import { SystemPage } from './pages/SystemPage'
import { WelcomePage } from './pages/WelcomePage'

/**
 * Route table. Auth-protected pages arrive with Phase 1 (Users/Auth); on
 * Phase 0 the login route is still present so navigation does not change
 * shape later.
 */
export function AppRoutes() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<WelcomePage />} />
        <Route path="/login" element={<PlaceholderPage title="Login" />} />
        <Route path="/projects" element={<PlaceholderPage title="Projects" />} />
        <Route path="/projects/:projectId" element={<PlaceholderPage title="Project" />} />
        <Route path="/projects/:projectId/tasks" element={<PlaceholderPage title="Tasks" />} />
        <Route path="/tasks/:taskId" element={<PlaceholderPage title="Task" />} />
        <Route path="/settings" element={<PlaceholderPage title="Settings" />} />
        <Route path="/system" element={<SystemPage />} />
        <Route path="*" element={<PlaceholderPage title="Not found" />} />
      </Routes>
    </AppShell>
  )
}

export function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}

function PlaceholderPage({ title }: { title: ReactNode }) {
  return (
    <section>
      <h1>{title}</h1>
      <p>Not implemented yet — see docs/architecture.md (roadmap).</p>
    </section>
  )
}