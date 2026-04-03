import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('BorgApiClient', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('uses v1 routes for non-v2 repositories', async () => {
    const clientModule = await import('./client')
    const getMock = vi.spyOn(clientModule.httpClient, 'get').mockResolvedValue({} as never)
    const postMock = vi.spyOn(clientModule.httpClient, 'post').mockResolvedValue({} as never)
    const deleteMock = vi.spyOn(clientModule.httpClient, 'delete').mockResolvedValue({} as never)
    const { BorgApiClient } = clientModule
    const client = new BorgApiClient({ id: 7, borg_version: 1 } as never)

    client.getInfo()
    client.listArchives()
    client.getArchiveInfo('archive-1')
    client.getArchiveContents('archive-id', 'archive-name', '/etc')
    client.deleteArchive('archive-1')
    client.getDeleteJobStatus(12)
    client.runBackup({ archive_name: 'nightly' })
    client.pruneArchives({ keep_daily: 7 })
    client.compact()
    client.checkRepository(30)
    const downloadUrl = client.getDownloadUrl('archive-1', '/etc/hosts')

    expect(getMock).toHaveBeenCalledWith('/repositories/7/info')
    expect(getMock).toHaveBeenCalledWith('/repositories/7/archives')
    expect(getMock).toHaveBeenCalledWith('/archives/archive-1/info', {
      params: { repository: 7, include_files: false, file_limit: 1000 },
    })
    expect(getMock).toHaveBeenCalledWith('/browse/7/archive-name', {
      params: { path: '/etc' },
    })
    expect(deleteMock).toHaveBeenCalledWith('/archives/archive-1', {
      params: { repository: 7 },
    })
    expect(getMock).toHaveBeenCalledWith('/archives/delete-jobs/12')
    expect(postMock).toHaveBeenCalledWith('/backup/run', {
      repository_id: 7,
      archive_name: 'nightly',
    })
    expect(postMock).toHaveBeenCalledWith('/repositories/7/prune', { keep_daily: 7 })
    expect(postMock).toHaveBeenCalledWith('/repositories/7/compact')
    expect(postMock).toHaveBeenCalledWith('/repositories/7/check', { max_duration: 30 })
    expect(downloadUrl).toContain('/api/archives/download?')
    expect(downloadUrl).toContain('repository=7')
    expect(downloadUrl).toContain('archive=archive-1')
    expect(downloadUrl).toContain('file_path=%2Fetc%2Fhosts')
  })

  it('uses v2 routes for Borg 2 repositories', async () => {
    const clientModule = await import('./client')
    const getMock = vi.spyOn(clientModule.httpClient, 'get').mockResolvedValue({} as never)
    const postMock = vi.spyOn(clientModule.httpClient, 'post').mockResolvedValue({} as never)
    const { BorgApiClient } = clientModule
    const client = new BorgApiClient({ id: 9, borg_version: 2 } as never)

    client.getArchiveContents('archive-id', 'ignored-name', '/srv')
    client.pruneArchives({ keep_weekly: 4 })
    client.compact()
    client.checkRepository()
    const downloadUrl = client.getDownloadUrl('archive-2', '/srv/data.txt')

    expect(getMock).toHaveBeenCalledWith('/v2/archives/archive-id/contents', {
      params: { repository: 9, path: '/srv' },
    })
    expect(postMock).toHaveBeenCalledWith('/v2/backup/prune', {
      repository_id: 9,
      keep_weekly: 4,
    })
    expect(postMock).toHaveBeenCalledWith('/v2/backup/compact', { repository_id: 9 })
    expect(postMock).toHaveBeenCalledWith('/v2/backup/check', {
      repository_id: 9,
    })
    expect(downloadUrl).toContain('/api/v2/archives/download?')
    expect(downloadUrl).toContain('repository=9')
    expect(downloadUrl).toContain('archive=archive-2')
    expect(downloadUrl).toContain('file_path=%2Fsrv%2Fdata.txt')
  })

  it('routes static create and import calls by borg version', async () => {
    const clientModule = await import('./client')
    const postMock = vi.spyOn(clientModule.httpClient, 'post').mockResolvedValue({} as never)
    const { BorgApiClient } = clientModule

    BorgApiClient.createRepository({ name: 'v1', borg_version: 1 } as never)
    BorgApiClient.createRepository({ name: 'v2', borg_version: 2 } as never)
    BorgApiClient.importRepository({ name: 'v1 import', borg_version: 1 } as never)
    BorgApiClient.importRepository({ name: 'v2 import', borg_version: 2 } as never)

    expect(postMock).toHaveBeenCalledWith('/repositories/', { name: 'v1', borg_version: 1 })
    expect(postMock).toHaveBeenCalledWith('/v2/repositories/', { name: 'v2', borg_version: 2 })
    expect(postMock).toHaveBeenCalledWith('/repositories/import', {
      name: 'v1 import',
      borg_version: 1,
    })
    expect(postMock).toHaveBeenCalledWith('/v2/repositories/import', {
      name: 'v2 import',
      borg_version: 2,
    })
  })
})
