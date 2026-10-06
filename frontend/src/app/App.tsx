import { BrowserRouter, Outlet, Route, Routes } from 'react-router-dom'

import { AuthProvider } from '../core/auth/AuthContext'
import { RequireAuth } from '../core/auth/RequireAuth'
import { I18nProvider } from '../core/i18n'
import { OrganizationProvider } from '../core/organizations/OrganizationContext'
import { AppShell } from '../core/layout/AppShell'
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PortalSettingsPage } from './pages/PortalSettingsPage'
import { ProjectPage } from './pages/ProjectPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { SystemPage } from './pages/SystemPage'
import { UserProfilePage } from './pages/UserProfilePage'
import { WelcomePage } from './pages/WelcomePage'
import { MembersPage } from '../core/organizations/MembersPage'
import { UsersPage } from '../core/users/UsersPage'
import { TaskDetailPage } from '../modules/tasks/pages/TaskDetailPage'
import { TaskListPage } from '../modules/tasks/pages/TaskListPage'

/**
 * The route table (section 29).
 *
 * Providers nest in the order their data depends on: translations are needed by
 * everything, the session decides what renders, and authenticated pages need an
 * organization to build a request.
 *
 * The guard wraps a route *group* rather than each page, so a new page cannot
 * ship unprotected by being added in the wrong place.
 */
export function App() {
  return (
    <I18nProvider>
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
                  <Route path="/users/me" element={<UserProfilePage />} />
                  <Route path="/members" element={<MembersPage />} />
                  <Route path="/users" element={<UsersPage />} />
                  <Route path="/settings" element={<PortalSettingsPage />} />
                </Route>

                <Route path="*" element={<NotFoundPage />} />
              </Routes>
            </AppShell>
          </OrganizationProvider>
        </AuthProvider>
      </BrowserRouter>
    </I18nProvider>
  )
}
