import { Link } from 'react-router-dom'

import { useAuth } from '../../core/auth/AuthContext'
import { useI18n } from '../../core/i18n'

/**
 * The public landing page.
 *
 * It checks the session rather than showing a fixed "sign in" link, because the
 * common visit is somebody returning to work, not somebody arriving for the first
 * time.
 */
export function WelcomePage() {
  const { t } = useI18n()
  const { status } = useAuth()

  return (
    <section className="landing">
      <h1>{t('app.name')}</h1>
      <p>{t('app.tagline')}</p>

      {status === 'authenticated' ? (
        <p>
          <Link className="button button--primary" to="/projects">
            {t('nav.projects')}
          </Link>
        </p>
      ) : (
        <p>
          <Link className="button button--primary" to="/login">
            {t('auth.signIn')}
          </Link>
        </p>
      )}

      <h2>{t('projects.title')}</h2>
      <ul>
        <li>{t('nav.projects')}</li>
        <li>{t('nav.allTasks')}</li>
        <li>{t('nav.members')}</li>
        <li>{t('comments.title')}</li>
        <li>{t('activity.title')}</li>
      </ul>
    </section>
  )
}
