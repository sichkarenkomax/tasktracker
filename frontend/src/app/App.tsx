import { useMemo } from 'react'
import type { ReactNode } from 'react'
import { BrowserRouter, Outlet, Route, Routes } from 'react-router-dom'

import { AuthProvider } from '../core/auth/AuthContext'
import { RequireAuth } from '../core/auth/RequireAuth'
import { DateFormatSync } from '../core/format/DateFormatSync'
import { I18nProvider } from '../core/i18n'
import { OrganizationProvider, useOrganization } from '../core/organizations/OrganizationContext'
import { AppShell } from '../core/layout/AppShell'
import { registerNavigatorGroup } from '../core/layout/navigator'
import { RailBadgesProvider } from '../core/layout/railBadges'
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PortalSettingsPage } from './pages/PortalSettingsPage'
import { PreferencesPage } from './pages/PreferencesPage'
import { ProjectPage } from './pages/ProjectPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { SystemPage } from './pages/SystemPage'
import { UserProfilePage } from './pages/UserProfilePage'
import { WelcomePage } from './pages/WelcomePage'
import { MembersPage } from '../core/organizations/MembersPage'
import { OrgStructurePage } from '../core/organizations/OrgStructurePage'
import { UsersPage } from '../core/users/UsersPage'
import { TaskDetailPage } from '../modules/tasks/pages/TaskDetailPage'
import { TaskCreatePage } from '../modules/tasks/pages/TaskCreatePage'
import { TaskListPage } from '../modules/tasks/pages/TaskListPage'
import { savedFiltersNavigatorGroup } from '../modules/tasks/components/SavedFiltersNavigatorGroup'
import { useOverdueCount } from '../modules/tasks/useOverdueCount'

// Navigator submenus are owned by the modules and wired in here, at the one
// layer allowed to import in both directions (stage 1.9).
registerNavigatorGroup(savedFiltersNavigatorGroup)

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
            <DateFormatSync />
            <RailBadges>
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
                  {/* Before `/tasks/:taskId`: React Router ranks the static segment
                      first anyway, and the comment keeps the next reader from
                      wondering whether the order matters (it is stated here
                      because it does for other routers). */}
                  <Route path="/tasks/new" element={<TaskCreatePage />} />
                  <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
                  <Route path="/projects/:projectId/tasks/new" element={<TaskCreatePage />} />
                  <Route path="/users/me" element={<UserProfilePage />} />
      <Route path="/preferences" element={<PreferencesPage />} />
                  <Route path="/members" element={<MembersPage />} />
                  <Route path="/structure" element={<OrgStructurePage />} />
                  <Route path="/users" element={<UsersPage />} />
                  <Route path="/settings" element={<PortalSettingsPage />} />
                </Route>

                <Route path="*" element={<NotFoundPage />} />
              </Routes>
              </AppShell>
            </RailBadges>
          </OrganizationProvider>
        </AuthProvider>
      </BrowserRouter>
    </I18nProvider>
  )
}

/**
 * The numbers the rail paints on its icons.
 *
 * The rail is in `core` and the overdue count belongs to the tasks module, so the
 * app layer is where the two meet: it asks the module, and hands `core` a plain
 * map. `core` learns nothing about tasks.
 */
function RailBadges({ children }: { children: ReactNode }) {
  const { current } = useOrganization()
  const overdue = useOverdueCount(current?.id ?? null)
  const value = useMemo(() => ({ tasks: overdue }), [overdue])
  return <RailBadgesProvider value={value}>{children}</RailBadgesProvider>
}
