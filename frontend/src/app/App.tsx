import { BrowserRouter, Outlet, Route, Routes } from 'react-router-dom'

import { AuthProvider } from '../core/auth/AuthContext'
import { RequireAuth } from '../core/auth/RequireAuth'
import { OrganizationProvider } from '../core/organizations/OrganizationContext'
import { AppShell } from '../core/layout/AppShell'
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { ProjectPage } from './pages/ProjectPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { SettingsPage } from './pages/SettingsPage'
import { SystemPage } from './pages/SystemPage'
import { WelcomePage } from './pages/WelcomePage'
import { TaskDetailPage } from '../modules/tasks/pages/TaskDetailPage'
import { TaskListPage } from '../modules/tasks/pages/TaskListPage'

/**
 * The route table (section 29).
 *
 * Providers nest in the order their data depends on: the shell needs the session
 * to decide what to render, and every authenticated page needs an organization to
 * build a request, so `AuthProvider` wraps `OrganizationProvider`.
 *
 * The guard wraps a route *group* rather than each page, so a new page cannot
 * accidentally ship unprotected by being added in the wrong place.
 */
export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <OrganizationProvider>
          <AppShell>
            <Routes>
              <Route path="/" element={<WelcomePage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/system" element={<SystemPage />} />

              <Route
                element={
                  <RequireAuth>
                    <Outlet />
                  </RequireAuth>
                }
              >
                <Route path="/projects" element={<ProjectsPage />} />
                <Route path="/projects/:projectId" element={<ProjectPage />} />
                <Route path="/projects/:projectId/tasks" element={<TaskListPage />} />
                <Route path="/tasks" element={<TaskListPage />} />
                <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Route>

              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </AppShell>
        </OrganizationProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
