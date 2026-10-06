import { Link } from 'react-router-dom'

import { useAuth } from '../../core/auth/AuthContext'

/**
 * The public landing page.
 *
 * It checks the session rather than showing a fixed "sign in" link, because the
 * common visit is somebody returning to work, not somebody arriving for the first
 * time.
 */
export function WelcomePage() {
  const { status } = useAuth()

  return (
    <section className="landing">
      <h1>TaskTracker</h1>
      <p>
        A self-hosted platform for managing work. Organizations hold projects, projects hold tasks,
        and every change is written to an activity feed your team can read back.
      </p>

      {status === 'authenticated' ? (
        <p>
          <Link className="button button--primary" to="/projects">
            Go to your projects
          </Link>
        </p>
      ) : (
        <p>
          <Link className="button button--primary" to="/login">
            Sign in or create an account
          </Link>
        </p>
      )}

      <h2>What works today</h2>
      <ul>
        <li>Accounts, organizations and roles: owner, admin, member, viewer.</li>
        <li>Projects, teams and comments.</li>
        <li>Tasks with status, priority, assignee and deadline.</li>
        <li>Search, filtering and sorting over the task list.</li>
        <li>An activity feed for every organization and every task.</li>
      </ul>
    </section>
  )
}
