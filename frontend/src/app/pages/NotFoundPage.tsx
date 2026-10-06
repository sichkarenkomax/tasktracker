import { Link } from 'react-router-dom'

import { useI18n } from '../../core/i18n'

export function NotFoundPage() {
  const { t } = useI18n()
  return (
    <section>
      <h1>{t('app.notFound')}</h1>
      <p className="muted">{t('app.notFoundBody')}</p>
      <ul>
        <li>
          <Link to="/projects">{t('nav.projects')}</Link>
        </li>
        <li>
          <Link to="/tasks">{t('nav.allTasks')}</Link>
        </li>
        <li>
          <Link to="/">{t('app.goHome')}</Link>
        </li>
      </ul>
    </section>
  )
}
