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

const SAFE_SHELL_ARG_PATTERN = /^[A-Za-z0-9_@%+=:,./-]+$/

/** A value as one shell word, quoted only when it needs it. */
export function shellQuote(value: string): string {
  if (value && SAFE_SHELL_ARG_PATTERN.test(value)) {
    return value
  }

  return `'${value.replace(/'/g, "'\\''")}'`
}

const getBorgBinary = (borgVersion: 1 | 2 = 1): string => (borgVersion === 2 ? 'borg2' : 'borg')

/**
 * How the remote Borg command reaches a command shown to the user. Borg 1
 * takes `--remote-path` on the command line; Borg 2 has no such option and
 * reads BORG_REMOTE_PATH from the environment, so the command gets the
 * variable in front of the binary. The value is quoted here: a
 * remote command such as `sudo -n -H /opt/borg2` holds spaces. Empty means no
 * remote path.
 */
export const remotePathParts = (
  borgVersion: 1 | 2,
  remotePath: string
): { flag: string; envPrefix: string } => {
  if (!remotePath) return { flag: '', envPrefix: '' }
  const quoted = shellQuote(remotePath)
  if (borgVersion === 2) return { flag: '', envPrefix: `BORG_REMOTE_PATH=${quoted} ` }
  return { flag: `--remote-path ${quoted} `, envPrefix: '' }
}

/**
 * Borg 2's repo-create takes the cipher and where the key is stored
 * (--key-location) as separate options. The combined names stay the
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
  // Without encryption the id hash is part of the mode name; `authenticated`
  // is the sha256 variant. Borg 2 has no `none`.
  authenticated: '--encryption authenticated-sha256',
}

/**
 * Whether Borg 2 can create a repository with a stored mode. Borg 2 has no
 * `none`; a repository recorded with it was created before the update to the
 * current Borg 2, which cannot read it (unknown modes pass through, see above).
 */
export const borg2CanCreateWith = (encryption: string): boolean => encryption !== 'none'

export const generateBorgInitCommand = (options: BorgInitCommandOptions): string => {
  const {
    repositoryPath,
    borgVersion = 1,
    encryption = borgVersion === 2 ? 'repokey-aes-ocb' : 'repokey',
    remotePathFlag = '',
  } = options

  if (borgVersion === 2) {
    const encryptionFlags = BORG2_ENCRYPTION_FLAGS[encryption] ?? `--encryption ${encryption}`
    return `${getBorgBinary(2)} -r ${shellQuote(repositoryPath)} repo-create ${remotePathFlag}${encryptionFlags}`
  }

  return `${getBorgBinary(1)} init --encryption ${encryption} ${remotePathFlag}${shellQuote(repositoryPath)}`
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
  const excludeArgs = excludePatterns
    .map((pattern: string) => `--exclude ${shellQuote(pattern)}`)
    .join(' ')
  const excludeStr = excludeArgs ? `${excludeArgs} ` : ''

  // Build custom flags with proper spacing
  const customFlagsStr = customFlags && customFlags.trim() ? ` ${customFlags.trim()} ` : ''

  // Build source directories string
  const sourceDirsStr = sourceDirs.map(shellQuote).join(' ')

  const commonOptions = `--progress --stats --compression ${compression} ${excludeStr}${customFlagsStr}`

  // Borg 2 takes the repository as -r and the archive name on its own;
  // repo::archive is Borg 1 syntax
  if (borgVersion === 2) {
    return `${getBorgBinary(2)} -r ${shellQuote(repositoryPath)} create ${remotePathFlag}${commonOptions}${archiveName} ${sourceDirsStr}`
  }

  return `${getBorgBinary(1)} create ${remotePathFlag}${commonOptions}${shellQuote(repositoryPath)}::${archiveName} ${sourceDirsStr}`
}
