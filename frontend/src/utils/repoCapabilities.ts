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
