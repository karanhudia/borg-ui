/**
 * Utility functions for generating Borg backup commands
 */

export interface BorgCommandOptions {
  repositoryPath: string
  compression?: string
  excludePatterns?: string[]
  sourceDirs?: string[]
  customFlags?: string
  remotePathFlag?: string
  archiveName?: string
}

/**
 * Generate a borg create command string
 * Used across Backup, Schedule, and Repositories tabs for consistent command generation
 */
export const generateBorgCreateCommand = (options: BorgCommandOptions): string => {
  const {
    repositoryPath,
    compression = 'lz4',
    excludePatterns = [],
    sourceDirs = ['/data'],
    customFlags = '',
    remotePathFlag = '',
    archiveName = '{hostname}-{now}',
  } = options

  // Build exclude patterns
  const excludeArgs = excludePatterns
    .map((pattern: string) => `--exclude '${pattern}'`)
    .join(' ')
  const excludeStr = excludeArgs ? `${excludeArgs} ` : ''

  // Build custom flags with proper spacing
  const customFlagsStr =
    customFlags && customFlags.trim() ? ` ${customFlags.trim()} ` : ''

  // Build source directories string
  const sourceDirsStr = sourceDirs.join(' ')

  // Construct the full command
  return `borg create ${remotePathFlag}--progress --stats --compression ${compression} ${excludeStr}${customFlagsStr}${repositoryPath}::${archiveName} ${sourceDirsStr}`
}
