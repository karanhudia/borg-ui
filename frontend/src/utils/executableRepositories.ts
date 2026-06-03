import type { Repository, SourceLocation } from '../types'

function hasSourceLocationPath(location: SourceLocation): boolean {
  if (location.paths?.some((path) => path.trim().length > 0)) return true
  return Boolean(location.database?.backup_paths?.some((path) => path.trim().length > 0))
}

export function isExecutableLegacyRepository(repository: Repository): boolean {
  if (repository.mode === 'observe') return false
  if (repository.source_directories?.some((path) => path.trim().length > 0)) return true
  return Boolean(repository.source_locations?.some(hasSourceLocationPath))
}

export function getExecutableLegacyRepositories(repositories: Repository[]): Repository[] {
  return repositories.filter(isExecutableLegacyRepository)
}
