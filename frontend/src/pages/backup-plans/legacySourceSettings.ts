import type { Repository } from '../../types'

export type LegacySourceComparison = 'matches' | 'plan_includes_legacy' | 'legacy_has_extra'

export interface LegacySourceRepositoryReview {
  repository: Repository
  legacySourceDirectories: string[]
  legacyOnlySourceDirectories: string[]
  planOnlySourceDirectories: string[]
  comparison: LegacySourceComparison
  defaultClear: boolean
}

function normalizePaths(paths: string[] = []): string[] {
  const seen = new Set<string>()
  return paths.reduce<string[]>((normalized, path) => {
    const trimmed = path.trim()
    if (!trimmed || seen.has(trimmed)) return normalized
    seen.add(trimmed)
    normalized.push(trimmed)
    return normalized
  }, [])
}

function difference(paths: string[], comparisonPaths: string[]): string[] {
  const comparisonSet = new Set(comparisonPaths)
  return paths.filter((path) => !comparisonSet.has(path))
}

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

export function getLegacySourceRepositoryReviews(
  repositories: Repository[],
  selectedRepositoryIds: number[],
  planSourceDirectories: string[]
): LegacySourceRepositoryReview[] {
  const normalizedPlanSources = normalizePaths(planSourceDirectories)

  return getLegacySourceRepositoryTargets(repositories, selectedRepositoryIds).map((repository) => {
    const legacySourceDirectories = normalizePaths(repository.source_directories)
    const legacyOnlySourceDirectories = difference(legacySourceDirectories, normalizedPlanSources)
    const planOnlySourceDirectories = difference(normalizedPlanSources, legacySourceDirectories)
    const defaultClear = legacyOnlySourceDirectories.length === 0
    const comparison: LegacySourceComparison =
      legacyOnlySourceDirectories.length > 0
        ? 'legacy_has_extra'
        : planOnlySourceDirectories.length > 0
          ? 'plan_includes_legacy'
          : 'matches'

    return {
      repository,
      legacySourceDirectories,
      legacyOnlySourceDirectories,
      planOnlySourceDirectories,
      comparison,
      defaultClear,
    }
  })
}
