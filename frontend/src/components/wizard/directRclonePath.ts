export interface DirectRclonePathParts {
  remoteName: string
  remotePath: string
}

const DIRECT_RCLONE_PREFIX = 'rclone:'
const LEGACY_DIRECT_RCLONE_PREFIX = 'rclone://'

export function normalizeRcloneRemotePath(path: string): string {
  return path.trim().replace(/^\/+/, '')
}

export function parseDirectRcloneUrl(value: string): DirectRclonePathParts | null {
  const trimmed = value.trim()
  const isLegacyUrl = trimmed.startsWith(LEGACY_DIRECT_RCLONE_PREFIX)
  if (!trimmed.startsWith(DIRECT_RCLONE_PREFIX)) return null

  const body = trimmed.slice(
    isLegacyUrl ? LEGACY_DIRECT_RCLONE_PREFIX.length : DIRECT_RCLONE_PREFIX.length
  )
  const separator = isLegacyUrl ? '/' : ':'
  const separatorIndex = body.indexOf(separator)
  const remoteName = (separatorIndex === -1 ? body : body.slice(0, separatorIndex)).trim()
  if (!remoteName) return null
  if (!isLegacyUrl && separatorIndex === -1) return null

  return {
    remoteName,
    remotePath:
      separatorIndex === -1 ? '' : normalizeRcloneRemotePath(body.slice(separatorIndex + 1)),
  }
}

export function formatDirectRcloneUrl(remoteName: string, remotePath: string): string {
  const normalizedRemoteName = typeof remoteName === 'string' ? remoteName.trim() : ''
  if (!normalizedRemoteName) {
    throw new Error('remoteName cannot be empty')
  }

  return `rclone:${normalizedRemoteName}:${normalizeRcloneRemotePath(remotePath)}`
}
