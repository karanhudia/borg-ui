// Deep-link hashes for the Schedule page. Used by the By Plan tab to take a
// user from a per-plan repository row directly to the matching row inside the
// Repository Checks / Restore Checks tabs.
//
// Hash format: `#repo-checks/<repoId>` or `#restore-checks/<repoId>`.

export type ScheduleDeepLinkTarget = 'repo-checks' | 'restore-checks'

export interface ScheduleDeepLink {
  target: ScheduleDeepLinkTarget
  repositoryId: number
}

export function buildScheduleDeepLink(
  target: ScheduleDeepLinkTarget,
  repositoryId: number
): string {
  return `#${target}/${repositoryId}`
}

export function parseScheduleDeepLink(hash: string): ScheduleDeepLink | null {
  const cleaned = hash.startsWith('#') ? hash.slice(1) : hash
  const match = cleaned.match(/^(repo-checks|restore-checks)\/(\d+)$/)
  if (!match) return null
  const repositoryId = Number.parseInt(match[2], 10)
  if (!Number.isFinite(repositoryId)) return null
  return {
    target: match[1] as ScheduleDeepLinkTarget,
    repositoryId,
  }
}
