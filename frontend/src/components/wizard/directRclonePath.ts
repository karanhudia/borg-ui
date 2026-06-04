export interface DirectRclonePathParts {
  remoteName: string
  remotePath: string
}

const DIRECT_RCLONE_PREFIX = 'rclone://'

export function normalizeRcloneRemotePath(path: string): string {
  return path.trim().replace(/^\/+/, '')
}

export function parseDirectRcloneUrl(value: string): DirectRclonePathParts | null {
  const trimmed = value.trim()
  if (!trimmed.startsWith(DIRECT_RCLONE_PREFIX)) return null

  const body = trimmed.slice(DIRECT_RCLONE_PREFIX.length)
  const firstSlashIndex = body.indexOf('/')
  const remoteName = (firstSlashIndex === -1 ? body : body.slice(0, firstSlashIndex)).trim()
  if (!remoteName) return null

  return {
    remoteName,
    remotePath:
      firstSlashIndex === -1 ? '' : normalizeRcloneRemotePath(body.slice(firstSlashIndex + 1)),
  }
}

export function formatDirectRcloneUrl(remoteName: string, remotePath: string): string {
  const normalizedRemoteName = typeof remoteName === 'string' ? remoteName.trim() : ''
  if (!normalizedRemoteName) {
    throw new Error('remoteName cannot be empty')
  }

  return `rclone://${normalizedRemoteName}/${normalizeRcloneRemotePath(remotePath)}`
}
