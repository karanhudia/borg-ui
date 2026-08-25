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

/**
 * Borg 2.0.0b22 split repo-create's single --encryption value into the cipher
 * and where the key is stored (--key-location). The combined names stay the
 * vocabulary of the UI and of the stored repository, so a command shown to the
 * user is translated here — the same table the server and the agent keep
 * (app/core/borg2.py, agent/borg_ui_agent/repository_ops.py). Three runtimes,
 * no shared module, so it is stated three times.
 *
 * A mode this table does not know is passed through: borg names the valid ones
 * in its own error, which beats this file inventing a flag.
 */
const BORG2_ENCRYPTION_FLAGS: Record<string, string> = {
  'repokey-aes-ocb': '--encryption aes256-ocb --key-location repokey',
  'repokey-chacha20-poly1305': '--encryption chacha20-poly1305 --key-location repokey',
  'keyfile-aes-ocb': '--encryption aes256-ocb --key-location keyfile',
  'keyfile-chacha20-poly1305': '--encryption chacha20-poly1305 --key-location keyfile',
  // b23 folded the id hash into the unencrypted mode names; the sha256
  // variants keep exactly what `authenticated`/`none` produced before.
  authenticated: '--encryption authenticated-sha256',
  none: '--encryption none-sha256',
}

export const generateBorgInitCommand = (options: BorgInitCommandOptions): string => {
  const {
    repositoryPath,
    borgVersion = 1,
    encryption = borgVersion === 2 ? 'repokey-aes-ocb' : 'repokey',
    remotePathFlag = '',
  } = options

  if (borgVersion === 2) {
    const encryptionFlags = BORG2_ENCRYPTION_FLAGS[encryption] ?? `--encryption ${encryption}`
    return `${getBorgBinary(2)} -r ${repositoryPath} repo-create ${remotePathFlag}${encryptionFlags}`
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
