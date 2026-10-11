import type { Department, Member, Placement } from './api'

/**
 * The two trees the org chart draws.
 *
 * Departments nest (Engineering contains Backend); people nest by who they report
 * to. They are separate trees over the same set of people, and conflating them is
 * the mistake this file exists to avoid: a department is a unit, a reporting line
 * is a relationship, and somebody can be the head of a department they do not
 * report to the head of.
 *
 * The layout is computed here rather than in the component so that the editor and
 * the read-only view are guaranteed to draw the same picture, and so a test can
 * assert on the geometry without a DOM.
 */

export interface ChartNode {
  kind: 'person'
  userId: string
  name: string
  /** Carried with the node so the box can draw the shared `Avatar` instead of a
   *  letter: the chart already holds the roster, the box does not. */
  avatarUrl: string | null
  title: string | null
  departmentId: string | null
  positionId: string | null
  deputyIds: string[]
  children: ChartNode[]
  depth: number
}

export interface ChartGroup {
  kind: 'department'
  departmentId: string
  name: string
  headId: string | null
  children: ChartGroup[]
  /** People in this department itself, in reporting order. Not the ones below it:
   *  those belong to their own group, and an expanded box lists a department's
   *  own people plus a box per child rather than one merged list that would say
   *  "Engineering has 40 people" when it has four and a Platform underneath. */
  people: ChartNode[]
  depth: number
}

/**
 * How many people the department accounts for, counting everything below it.
 *
 * What a collapsed card shows. The number of direct members would answer a
 * different question: "Platform has 3" beside an obviously large Engineering
 * reads as "Engineering is empty", and collapsing is what somebody does to
 * find out how much is hidden.
 */
export function peopleInSubtree(group: ChartGroup): number {
  return (
    group.people.length +
    group.children.reduce((total, child) => total + peopleInSubtree(child), 0)
  )
}

export interface Chart {
  roots: ChartGroup[]
  /** Members not reachable from any department, so nothing silently vanishes. */
  unplaced: ChartNode[]
}

/**
 * Build the chart from the API payload.
 *
 * Ordering is deliberate at every level: departments in the position an
 * administrator gave them, people under their manager and alphabetically within
 * a manager. Ordering by id would be stable but meaningless; ordering only by name
 * would move boxes around whenever somebody's name changed.
 */
export function buildChart(
  departments: Department[],
  members: Member[],
  placements: Record<string, Placement>,
): Chart {
  const nameOf = new Map(members.map((member) => [member.user_id, displayName(member)]))

  // --- people, by reporting line -----------------------------------------
  const nodes = new Map<string, ChartNode>()
  for (const member of members) {
    const placement = placements[member.user_id]
    nodes.set(member.user_id, {
      kind: 'person',
      userId: member.user_id,
      name: nameOf.get(member.user_id) ?? member.username,
      avatarUrl: member.avatar_url,
      title: placement?.position_id ?? null,
      departmentId: placement?.department_id ?? null,
      positionId: placement?.position_id ?? null,
      deputyIds: placement?.deputies ?? [],
      children: [],
      depth: 0,
    })
  }

  const roots: ChartNode[] = []
  for (const node of nodes.values()) {
    const managerId = placements[node.userId]?.manager_id ?? null
    const manager = managerId ? nodes.get(managerId) : undefined
    if (manager && manager !== node) {
      manager.children.push(node)
    } else {
      roots.push(node)
    }
  }

  const byName = (a: ChartNode, b: ChartNode) => a.name.localeCompare(b.name)
  const sortDeep = (list: ChartNode[]) => {
    list.sort(byName)
    for (const node of list) sortDeep(node.children)
  }
  sortDeep(roots)

  // --- departments ------------------------------------------------------
  const groups = new Map<string, ChartGroup>()
  for (const department of departments) {
    groups.set(department.id, {
      kind: 'department',
      departmentId: department.id,
      name: department.name,
      headId: department.head_id,
      children: [],
      people: [],
      depth: 0,
    })
  }

  const groupRoots: ChartGroup[] = []
  for (const department of departments) {
    const group = groups.get(department.id)!
    const parent = department.parent_id ? groups.get(department.parent_id) : undefined
    // A department whose parent is missing - deleted, or filtered out - is drawn
    // at the top rather than dropped, so an inconsistent chart is visible
    // instead of looking like data loss.
    if (parent && parent !== group) {
      parent.children.push(group)
    } else {
      groupRoots.push(group)
    }
  }

  const sortGroups = (list: ChartGroup[]) => {
    list.sort((a, b) => a.name.localeCompare(b.name))
    for (const group of list) sortGroups(group.children)
  }
  sortGroups(groupRoots)

  // People land in the department they belong to. A member with no department
  // goes to `unplaced` rather than being attached to the first group that happens
  // to exist.
  //
  // Exactly one department claims each person, checked rather than assumed: the
  // nested groups are visited from the outside in, so an inner box cannot claim
  // somebody an outer box already took. Without that check the same name appeared
  // twice - once in the department it belonged to and once in a parent that was
  // only being drawn because it contains other departments.
  const assigned = new Set<string>()
  const assign = (group: ChartGroup) => {
    for (const node of nodes.values()) {
      if (node.departmentId === group.departmentId && !assigned.has(node.userId)) {
        group.people.push(node)
        assigned.add(node.userId)
      }
    }
    group.people.sort(byName)
    // Children after this group: a parent is drawn before its children, so
    // whichever box comes first in the document keeps the person.
    for (const child of group.children) assign(child)
  }
  for (const group of groupRoots) assign(group)

  const unplaced: ChartNode[] = []
  for (const node of roots) {
    if (!assigned.has(node.userId)) unplaced.push(node)
  }

  return { roots: groupRoots, unplaced }
}

/**
 * Would making ``managerId`` the manager of ``userId`` close a loop?
 *
 * Walking up from the proposed manager answers it: a loop exists exactly when
 * the person being moved is already an ancestor. The server refuses the same
 * write; this is the half that makes the drop do nothing visibly instead of
 * showing an error the person did not cause by a wrong drag.
 */
export function wouldReportLoop(
  placements: Record<string, Placement>,
  userId: string,
  managerId: string,
): boolean {
  const seen = new Set<string>()
  let cursor: string | null = managerId
  while (cursor && !seen.has(cursor)) {
    if (cursor === userId) return true
    seen.add(cursor)
    cursor = placements[cursor]?.manager_id ?? null
  }
  return false
}

/** The same person, as the list renders them. */
export function displayName(member: Member): string {
  return member.first_name || member.username
}

/**
 * The name of one person, looked up in a roster that may not contain them.
 *
 * For places that hold ids rather than members - a department's head and its
 * deputies, both of which can name somebody who has since left - and cannot
 * crash on one that does not. The id itself is the fallback: a row reading a
 * uuid is ugly, but a chart that throws because a deputy was removed elsewhere
 * is worse.
 */
export function memberName(members: ReadonlyArray<Member>, userId: string | null): string | null {
  if (userId === null) return null
  const member = members.find((item) => item.user_id === userId)
  return member ? displayName(member) : userId
}

/**
 * A department id together with everything nested under it.
 *
 * The re-parent guard needs it in both places that accept a drop: the chart,
 * which refuses the gesture before a request goes out, and the parent picker in
 * the inspector, which leaves the impossible options out entirely. The server
 * checks the same thing, but a drop that visibly does nothing is a bug report
 * waiting to happen.
 */
export function departmentSubtree(departments: Department[], departmentId: string): Set<string> {
  const children = new Map<string | null, string[]>()
  for (const department of departments) {
    const list = children.get(department.parent_id) ?? []
    list.push(department.id)
    children.set(department.parent_id, list)
  }

  const result = new Set<string>()
  const walk = (id: string) => {
    if (result.has(id)) return
    result.add(id)
    for (const child of children.get(id) ?? []) walk(child)
  }
  walk(departmentId)
  return result
}

/** Ids ordered as the editor draws them: parents, then their children. */
export function flattenDepartments(departments: Department[]): Array<{
  department: Department
  depth: number
}> {
  const children = new Map<string | null, Department[]>()
  for (const department of departments) {
    const list = children.get(department.parent_id) ?? []
    list.push(department)
    children.set(department.parent_id, list)
  }

  const rows: Array<{ department: Department; depth: number }> = []
  const visited = new Set<string>()
  const walk = (department: Department, depth: number) => {
    if (visited.has(department.id)) return
    visited.add(department.id)
    rows.push({ department, depth })
    for (const child of children.get(department.id) ?? []) walk(child, depth + 1)
  }
  // A department whose parent is missing stays visible at the top level rather
  // than disappearing, exactly as the chart draws it.
  for (const department of departments) {
    if (department.parent_id === null || !departments.some((item) => item.id === department.parent_id)) {
      walk(department, 0)
    }
  }
  for (const department of departments) walk(department, 0)
  return rows
}
