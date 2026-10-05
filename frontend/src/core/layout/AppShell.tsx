/** Shared layout: header + navigation shell (docs/architecture.md, section 29). */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <header className="app-shell__header">
        <strong>TaskTracker</strong>
        <nav className="app-shell__nav">
          <a href="/projects">Projects</a>
          <a href="/settings">Settings</a>
        </nav>
      </header>
      <main className="app-shell__main">{children}</main>
    </div>
  )
}