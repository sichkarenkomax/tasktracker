import { useMemo } from 'react'
import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'

import { AuthProvider } from '../core/auth/AuthContext'
import { RequireAuth } from '../core/auth/RequireAuth'
import { SettingsSync } from '../core/format/SettingsSync'
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
import { MemberProfilePage } from './pages/MemberProfilePage'
import { UserProfilePage } from './pages/UserProfilePage'
import { WelcomePage } from './pages/WelcomePage'
import { OrgStructurePage } from '../core/organizations/OrgStructurePage'
import { PeoplePage } from '../core/users/PeoplePage'
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
            <SettingsSync />
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
                  {/* Before `/users/me`: React Router ranks the static segment first, but a
                      colleague's profile is a different screen from one's own. */}
                  <Route path="/users/:userId" element={<MemberProfilePage />} />
                  <Route path="/users/me" element={<UserProfilePage />} />
                  <Route path="/preferences" element={<PreferencesPage />} />
                  <Route path="/structure" element={<OrgStructurePage />} />
                  {/* One people list (2.17): the old `/users` directory and the `/members` roster
                      are one screen now. `/members` redirects rather than 404ing - the
                      link exists in bookmarks, in old tickets and in people's heads. */}
                  <Route path="/users" element={<PeoplePage />} />
                  <Route path="/members" element={<Navigate to="/users" replace />} />
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
