import type { Repository } from '../../types'

export function getLegacySourceRepositoryTargets(
  repositories: Repository[],
  selectedRepositoryIds: number[]
): Repository[] {
  const selectedIds = new Set(selectedRepositoryIds)
  return repositories.filter(
    (repository) =>
      selectedIds.has(repository.id) &&
      Array.isArray(repository.source_directories) &&
      repository.source_directories.length > 0
  )
}
