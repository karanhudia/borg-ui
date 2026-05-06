export type RestoreLayout = 'preserve_path' | 'contents_only'
export type RestorePathType = 'file' | 'directory'

export interface RestorePathMetadata {
  path: string
  type: RestorePathType
}

export interface RestorePreviewOptions {
  restoreStrategy: 'original' | 'custom'
  customPath?: string | null
  restoreLayout?: RestoreLayout
  selectedItems?: RestorePathMetadata[]
  sshPrefix?: string
}

export const DEFAULT_RESTORE_LAYOUT: RestoreLayout = 'preserve_path'

export function normalizeArchivePath(path: string): string {
  return path
    .split('/')
    .filter((part) => part.length > 0)
    .join('/')
}

function pathComponents(path: string): string[] {
  const normalized = normalizeArchivePath(path)
  return normalized ? normalized.split('/') : []
}

function ensureAbsolutePath(path: string): string {
  if (!path) return '/'
  return path.startsWith('/') ? path : `/${path}`
}

function joinRestorePath(basePath: string, relativePath: string): string {
  const cleanBase = basePath.replace(/\/+$/, '')
  const cleanRelative = relativePath.replace(/^\/+/, '')

  if (!cleanBase) {
    return cleanRelative ? `/${cleanRelative}` : '/'
  }

  return cleanRelative ? `${cleanBase}/${cleanRelative}` : cleanBase
}

function commonPrefix(paths: string[][]): string[] {
  if (paths.length === 0) return []

  const [firstPath, ...restPaths] = paths
  const prefix: string[] = []

  for (const [index, component] of firstPath.entries()) {
    if (restPaths.every((path) => path[index] === component)) {
      prefix.push(component)
    } else {
      break
    }
  }

  return prefix
}

function getMetadataForPath(
  path: string,
  selectedItems: RestorePathMetadata[] = []
): RestorePathMetadata | undefined {
  const normalizedPath = normalizeArchivePath(path)
  return selectedItems.find((item) => normalizeArchivePath(item.path) === normalizedPath)
}

export function getRestoreStripComponentsForPreview(
  paths: string[],
  selectedItems: RestorePathMetadata[] = []
): number {
  const normalizedPaths = paths.map(normalizeArchivePath).filter(Boolean)
  if (normalizedPaths.length === 0) return 0

  if (normalizedPaths.length === 1) {
    const path = normalizedPaths[0]
    const itemType = getMetadataForPath(path, selectedItems)?.type || 'file'
    const componentCount = pathComponents(path).length

    return itemType === 'directory' ? componentCount : Math.max(componentCount - 1, 0)
  }

  const parentPaths = normalizedPaths.map((path) => pathComponents(path).slice(0, -1))
  return commonPrefix(parentPaths).length
}

export function getContentsOnlyRelativePath(
  path: string,
  selectedItems: RestorePathMetadata[] = []
): string {
  const normalizedPath = normalizeArchivePath(path)
  const selectedPaths = selectedItems.length > 0 ? selectedItems.map((item) => item.path) : [path]
  const stripComponents = getRestoreStripComponentsForPreview(selectedPaths, selectedItems)

  return pathComponents(normalizedPath).slice(stripComponents).join('/')
}

export function getRestorePreviewDestination(
  path: string,
  {
    restoreStrategy,
    customPath,
    restoreLayout = DEFAULT_RESTORE_LAYOUT,
    selectedItems = [],
    sshPrefix = '',
  }: RestorePreviewOptions
): string {
  let destinationPath: string

  if (restoreStrategy === 'custom' && customPath) {
    const relativePath =
      restoreLayout === 'contents_only'
        ? getContentsOnlyRelativePath(path, selectedItems)
        : normalizeArchivePath(path)

    destinationPath = joinRestorePath(customPath, relativePath)
  } else {
    destinationPath = ensureAbsolutePath(normalizeArchivePath(path))
  }

  const absolutePath = ensureAbsolutePath(destinationPath)
  return sshPrefix ? `${sshPrefix}${absolutePath}` : absolutePath
}
