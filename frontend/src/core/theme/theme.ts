/**
 * Theme choice (stage 1.1).
 *
 * Two themes live under one `data-theme` attribute on <html>: `gold` (the
 * default, a fixed dark palette) and `blue` (the original palette, which still
 * follows the operating system's light/dark mode inside its own block).
 *
 * The initial value is applied by an inline script in index.html before the
 * stylesheet loads, so this module only handles the profile switcher and the
 * same write it performs. No context: the theme is a property of the document,
 * not of the component tree, and nothing needs to re-render when it changes.
 */

export type Theme = 'gold' | 'blue'

export const DEFAULT_THEME: Theme = 'gold'

const STORAGE_KEY = 'tasktracker.theme'

export function getTheme(): Theme {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored === 'gold' || stored === 'blue') return stored
  } catch {
    // Locked-down profiles refuse localStorage; fall through to the default.
  }
  return DEFAULT_THEME
}

export function setTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
  try {
    window.localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    /* preference only */
  }
}
