/**
 * Utility functions for generating Borg backup commands
 */

export interface BorgCommandOptions {
  repositoryPath: string
  borgVersion?: 1 | 2
  compression?: string
  excludePatterns?: string[]
  sourceDirs?: string[]
  customFlags?: string
  remotePathFlag?: string
  archiveName?: string
}

export interface BorgInitCommandOptions {
  repositoryPath: string
  borgVersion?: 1 | 2
  encryption?: string
  remotePathFlag?: string
}

const getBorgBinary = (borgVersion: 1 | 2 = 1): string => (borgVersion === 2 ? 'borg2' : 'borg')

export const generateBorgInitCommand = (options: BorgInitCommandOptions): string => {
  const {
    repositoryPath,
    borgVersion = 1,
    encryption = borgVersion === 2 ? 'repokey-aes-ocb' : 'repokey',
    remotePathFlag = '',
  } = options

  if (borgVersion === 2) {
    return `${getBorgBinary(2)} -r ${repositoryPath} repo-create ${remotePathFlag}--encryption ${encryption}`
  }

  return `${getBorgBinary(1)} init --encryption ${encryption} ${remotePathFlag}${repositoryPath}`
}

/**
 * Generate a borg create command string
 * Used across Backup, Schedule, and Repositories tabs for consistent command generation
 */
export const generateBorgCreateCommand = (options: BorgCommandOptions): string => {
  const {
    repositoryPath,
    borgVersion = 1,
    compression = 'lz4',
    excludePatterns = [],
    sourceDirs = ['/data'],
    customFlags = '',
    remotePathFlag = '',
    archiveName = '{hostname}-{now}',
  } = options

  // Build exclude patterns
  const excludeArgs = excludePatterns.map((pattern: string) => `--exclude '${pattern}'`).join(' ')
  const excludeStr = excludeArgs ? `${excludeArgs} ` : ''

  // Build custom flags with proper spacing
  const customFlagsStr = customFlags && customFlags.trim() ? ` ${customFlags.trim()} ` : ''

  // Build source directories string
  const sourceDirsStr = sourceDirs.join(' ')

  // Construct the full command
  return `${getBorgBinary(borgVersion)} create ${remotePathFlag}--progress --stats --compression ${compression} ${excludeStr}${customFlagsStr}${repositoryPath}::${archiveName} ${sourceDirsStr}`
}
