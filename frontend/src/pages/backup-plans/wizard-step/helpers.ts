import type { SSHConnection } from '../types'

export function getPathBasename(path: string): string {
  if (!path) return path
  const trimmed = path.replace(/\/+$/, '')
  const lastSlash = trimmed.lastIndexOf('/')
  if (lastSlash < 0) return trimmed
  const basename = trimmed.slice(lastSlash + 1)
  return basename || trimmed
}

export function formatSshConnectionLabel(connection: SSHConnection): string {
  return `${connection.username}@${connection.host}:${connection.port}`
}
