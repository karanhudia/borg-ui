export function isV2Repo(repo: { borg_version?: number } | null | undefined): boolean {
  return repo?.borg_version === 2
}

export function getBorgVersion(repo: { borg_version?: number } | null | undefined): 1 | 2 {
  return repo?.borg_version === 2 ? 2 : 1
}

export function getRepoCapabilities(repo: Record<string, unknown> | { mode?: 'full' | 'observe' }) {
  const isObserve = repo.mode === 'observe'
  return {
    canBackup: !isObserve,
    canPrune: !isObserve,
    canCompact: !isObserve,
    canDelete: !isObserve,
    canMount: true,
    canRestore: true,
  }
}
