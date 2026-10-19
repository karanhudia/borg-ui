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

/**
 * Repository URLs only Borg 2 can open. Borg 1 refuses none of them: it reads
 * the `scheme://` forms as a local directory and the `name:` forms as an ssh
 * host of that name. The server refuses them for a Borg 1 repository with the
 * same list (BORG2_ONLY_URL_PREFIXES in app/api/repositories.py).
 */
export const BORG2_ONLY_URL_PREFIXES = [
  'rest://',
  'sftp://',
  'http://',
  'https://',
  's3:',
  'b2:',
  'rclone:',
] as const

/** Whether a repository path is a URL only Borg 2 can open. */
export const isBorg2OnlyUrl = (path: string): boolean => {
  const lowered = path.trim().toLowerCase()
  return BORG2_ONLY_URL_PREFIXES.some((prefix) => lowered.startsWith(prefix))
}

/**
 * Borg 2 reads what follows the host of an ssh:// URL as relative to the login
 * directory of the SSH user and takes a second slash for an absolute path:
 * `ssh://host/backups/repo` and `ssh://host//srv/backups/repo`. Borg 1 reads
 * the first as absolute. The repository form therefore writes a Borg 2 path
 * the way the server reads a plain one (app/core/borg2.py, `_borg2_path`): a
 * leading slash is absolute, anything else relative to the login directory,
 * as is Borg 1's spelling of it, `/./backups/repo`.
 */
export const borg2PathIsAbsolute = (path: string): boolean =>
  path.startsWith('/') && path !== '/.' && !path.startsWith('/./')

/**
 * The form's spelling (see above) of what follows the host of a Borg 2 URL.
 * An absolute tail loses its `./` steps, which the form would read as the
 * login directory: `//./srv/repo` is `/srv/repo`. The login directory itself
 * (`ssh://host/`) is `.`, which the server reads back the same.
 */
export const borg2PathFromUrlTail = (tail: string): string => {
  if (tail.startsWith('//')) {
    return `/${tail.replace(/^\/+/, '').replace(/^(\.(\/+|$))+/, '')}`
  }
  return tail.replace(/^\//, '') || '.'
}

/** Whether a Borg 2 ssh:// URL names an absolute path, or null for no ssh:// URL. */
export const borg2SshUrlIsAbsolute = (url: string): boolean | null => {
  const match = url.trim().match(/^ssh:\/\/[^/]+(\/.*)?$/i)
  if (!match) return null
  return (match[1] || '').startsWith('//')
}

/** What follows the host of a Borg 2 URL for a path written the form's way. */
export const borg2UrlTail = (path: string): string =>
  `${borg2PathIsAbsolute(path) ? '//' : '/'}${path.replace(/^\/+/, '')}`

/** The ssh:// URL of a Borg 2 repository at a path written the form's way. */
export const borg2SshUrl = (username: string, host: string, port: number, path: string): string =>
  `ssh://${username}@${host}:${port}${borg2UrlTail(path)}`

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
