import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <section>
      <h1>Page not found</h1>
      <p className="muted">
        That address does not match anything in TaskTracker. It may have been renamed, or the link
        may belong to a different installation.
      </p>
      <ul>
        <li>
          <Link to="/projects">Projects</Link>
        </li>
        <li>
          <Link to="/tasks">All tasks</Link>
        </li>
        <li>
          <Link to="/">Start here</Link>
        </li>
      </ul>
    </section>
  )
}
