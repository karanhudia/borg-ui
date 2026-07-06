import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { downloadArchiveFile } from '../downloadArchiveFile'
import { BorgApiClient, type Repository } from '../../services/borgApi/client'
import { toast } from 'react-hot-toast'

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual<typeof import('react-hot-toast')>('react-hot-toast')
  return {
    ...actual,
    toast: {
      loading: vi.fn(() => 'toast-id'),
      success: vi.fn(),
      error: vi.fn(),
    },
  }
})

const repo = { id: 3, borg_version: 1, path: '/repo' } as unknown as Repository

describe('downloadArchiveFile', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    global.URL.createObjectURL = vi.fn(() => 'blob:mock')
    global.URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('saves the file with its basename and shows a success toast', async () => {
    vi.spyOn(BorgApiClient.prototype, 'fetchArchiveFile').mockResolvedValue({
      data: new Blob(['hello']),
    } as never)
    const createElement = vi.spyOn(document, 'createElement')

    await downloadArchiveFile(repo, 'archive-1', 'node/var/lib/etcd-snapshot-m3s02')

    const anchor = createElement.mock.results
      .map((r) => r.value as HTMLElement)
      .find((el) => el.tagName === 'A') as HTMLAnchorElement | undefined
    expect(anchor?.download).toBe('etcd-snapshot-m3s02')
    expect(global.URL.createObjectURL).toHaveBeenCalledTimes(1)
    expect(toast.success).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ id: 'toast-id' })
    )
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('reports progress as a percentage when a total size is known', async () => {
    vi.spyOn(BorgApiClient.prototype, 'fetchArchiveFile').mockImplementation(
      (_archiveId, _filePath, options) => {
        options?.onDownloadProgress?.({
          loaded: 5 * 1024 * 1024,
          total: 10 * 1024 * 1024,
        } as never)
        return Promise.resolve({ data: new Blob(['x']) } as never)
      }
    )

    await downloadArchiveFile(repo, 'archive-1', 'big.bin')

    expect(toast.loading).toHaveBeenCalledWith(
      expect.stringContaining('50%'),
      expect.objectContaining({ id: 'toast-id' })
    )
  })

  it('surfaces a localised backend error parsed from a Blob error body', async () => {
    const errorBody = new Blob(
      [JSON.stringify({ detail: { key: 'backend.errors.jobs.repositoryOperationActive' } })],
      { type: 'application/json' }
    )
    vi.spyOn(BorgApiClient.prototype, 'fetchArchiveFile').mockRejectedValue({
      response: { data: errorBody },
    })

    await downloadArchiveFile(repo, 'archive-1', 'file.txt')

    expect(toast.error).toHaveBeenCalledWith(
      'Another operation is already running on this repository. Please wait for it to finish and try again.',
      expect.objectContaining({ id: 'toast-id' })
    )
    expect(global.URL.createObjectURL).not.toHaveBeenCalled()
  })

  it('falls back to a generic message when the error body is not parseable', async () => {
    vi.spyOn(BorgApiClient.prototype, 'fetchArchiveFile').mockRejectedValue({
      response: { data: new Blob(['not json']) },
    })

    await downloadArchiveFile(repo, 'archive-1', 'file.txt')

    expect(toast.error).toHaveBeenCalledWith(
      'Failed to download file',
      expect.objectContaining({ id: 'toast-id' })
    )
  })

  it('falls back to a generic message on a network error with no response', async () => {
    vi.spyOn(BorgApiClient.prototype, 'fetchArchiveFile').mockRejectedValue(
      new Error('Network Error')
    )

    await downloadArchiveFile(repo, 'archive-1', 'file.txt')

    expect(toast.error).toHaveBeenCalledWith(
      'Failed to download file',
      expect.objectContaining({ id: 'toast-id' })
    )
  })
})
