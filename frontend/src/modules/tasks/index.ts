/**
 * Tasks module (frontend side).
 *
 * The backend registers the module through its manifest; this folder mirrors
 * that structure so the Tasks UI can be added in Phase 2 without touching the
 * application shell (docs/architecture.md, sections 22 and 28).
 *
 * Planned layout:
 *   components/  - list, row, editor, filters
 *   pages/       - /projects/:projectId/tasks, /tasks/:taskId
 *   api/         - typed wrappers over core/api/client
 *   types/       - Task, TaskStatus, TaskPriority
 */
export {}