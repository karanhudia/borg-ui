import { describe, expect, it } from 'vitest'
import {
  getContentsOnlyRelativePath,
  getRestorePreviewDestination,
  getRestoreStripComponentsForPreview,
  normalizeArchivePath,
  type RestorePathMetadata,
} from './restorePaths'

describe('restore path previews', () => {
  it('normalizes archive paths without leading slashes', () => {
    expect(normalizeArchivePath('/home//username/folder/')).toBe('home/username/folder')
  })

  it('preserves the full archive path under a custom destination by default', () => {
    const selectedItems: RestorePathMetadata[] = [
      { path: 'home/username/folder1/folder2', type: 'directory' },
    ]

    expect(
      getRestorePreviewDestination('home/username/folder1/folder2', {
        restoreStrategy: 'custom',
        customPath: '/recovery/folder1/folder2',
        selectedItems,
      })
    ).toBe('/recovery/folder1/folder2/home/username/folder1/folder2')
  })

  it('restores a selected directory contents directly into the custom destination', () => {
    const selectedItems: RestorePathMetadata[] = [
      { path: 'home/username/folder1/folder2', type: 'directory' },
    ]

    expect(
      getRestorePreviewDestination('home/username/folder1/folder2', {
        restoreStrategy: 'custom',
        customPath: '/recovery/folder1/folder2',
        restoreLayout: 'contents_only',
        selectedItems,
      })
    ).toBe('/recovery/folder1/folder2')
    expect(getContentsOnlyRelativePath('home/username/folder1/folder2', selectedItems)).toBe('')
    expect(
      getRestoreStripComponentsForPreview(['home/username/folder1/folder2'], selectedItems)
    ).toBe(4)
  })

  it('restores a selected file into the custom destination while keeping the filename', () => {
    const selectedItems: RestorePathMetadata[] = [
      { path: 'home/username/folder1/report.txt', type: 'file' },
    ]

    expect(
      getRestorePreviewDestination('home/username/folder1/report.txt', {
        restoreStrategy: 'custom',
        customPath: '/recovery',
        restoreLayout: 'contents_only',
        selectedItems,
      })
    ).toBe('/recovery/report.txt')
  })

  it('keeps multiple selected directory names under their shared parent', () => {
    const selectedItems: RestorePathMetadata[] = [
      { path: 'home/username/folder1', type: 'directory' },
      { path: 'home/username/folder2', type: 'directory' },
    ]

    expect(
      getRestorePreviewDestination('home/username/folder1', {
        restoreStrategy: 'custom',
        customPath: '/recovery',
        restoreLayout: 'contents_only',
        selectedItems,
      })
    ).toBe('/recovery/folder1')
    expect(
      getRestorePreviewDestination('home/username/folder2', {
        restoreStrategy: 'custom',
        customPath: '/recovery',
        restoreLayout: 'contents_only',
        selectedItems,
      })
    ).toBe('/recovery/folder2')
  })

  it('adds the ssh prefix to restore previews without changing path math', () => {
    const selectedItems: RestorePathMetadata[] = [
      { path: 'home/username/report.txt', type: 'file' },
    ]

    expect(
      getRestorePreviewDestination('home/username/report.txt', {
        restoreStrategy: 'custom',
        customPath: '/restore',
        restoreLayout: 'contents_only',
        selectedItems,
        sshPrefix: 'ssh://root@example.com:22',
      })
    ).toBe('ssh://root@example.com:22/restore/report.txt')
  })
})
