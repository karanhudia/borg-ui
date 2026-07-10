import MockAdapter from 'axios-mock-adapter'
import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('BorgApiClient', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('attaches X-Borg-Authorization on httpClient requests', async () => {
    const clientModule = await import('./client')
    const mock = new MockAdapter(clientModule.httpClient)
    localStorage.setItem('access_token', 'client-token')

    mock.onGet('/test').reply((config) => {
      expect(config.headers?.['X-Borg-Authorization']).toBe('Bearer client-token')
      return [200, { success: true }]
    })

    await clientModule.httpClient.get('/test')
    mock.restore()
  })

  it('uses the active remote backend API base on httpClient requests', async () => {
    const {
      createRemoteBackendClient,
      setActiveBackendTarget,
      setBackendAccessToken,
      resetRemoteBackendStateForTests,
    } = await import('../remoteBackends/storage')
    resetRemoteBackendStateForTests()
    localStorage.setItem('access_token', 'local-token')
    const remote = createRemoteBackendClient({
      name: 'Remote',
      backendUrl: 'https://remote.example.com',
    })
    setActiveBackendTarget(remote.id)
    setBackendAccessToken('remote-token', remote.id)

    const clientModule = await import('./client')
    const mock = new MockAdapter(clientModule.httpClient)

    mock.onGet('/test').reply((config) => {
      expect(config.baseURL).toBe(`/api/remote-clients/${remote.id}/proxy/api`)
      expect(config.headers?.['X-Borg-Authorization']).toBe('Bearer local-token')
      expect(config.headers?.['X-Borg-Remote-Authorization']).toBe('Bearer remote-token')
      return [200, { success: true }]
    })

    await clientModule.httpClient.get('/test')
    mock.restore()
  })

  it('fetches archive files as a blob for the current backend', async () => {
    const clientModule = await import('./client')
    const getMock = vi.spyOn(clientModule.httpClient, 'get').mockResolvedValue({} as never)
    const { BorgApiClient } = clientModule
    const client = new BorgApiClient({ id: 9, borg_version: 2 } as never)

    client.fetchArchiveFile('archive-2', '/srv/data.txt')

    expect(getMock).toHaveBeenCalledWith('/v2/archives/download', {
      params: { repository: 9, archive: 'archive-2', file_path: '/srv/data.txt' },
      responseType: 'blob',
    })
  })

  it('uses v1 routes for non-v2 repositories', async () => {
    const clientModule = await import('./client')
    const getMock = vi.spyOn(clientModule.httpClient, 'get').mockResolvedValue({} as never)
    const postMock = vi.spyOn(clientModule.httpClient, 'post').mockResolvedValue({} as never)
    const deleteMock = vi.spyOn(clientModule.httpClient, 'delete').mockResolvedValue({} as never)
    const { BorgApiClient } = clientModule
    const client = new BorgApiClient({ id: 7, borg_version: 1, path: '/repo-v1' } as never)

    client.getInfo()
    client.listArchives()
    client.getArchiveInfo('archive-1')
    client.getArchiveContents('archive-id', 'archive-name', '/etc')
    client.deleteArchive('archive-1')
    client.getDeleteJobStatus(12)
    client.runBackup({ archive_name: 'nightly' })
    client.pruneArchives({ keep_daily: 7, keep_within: '1d' })
    client.compact()
    client.checkRepository(30)
    client.fetchArchiveFile('archive-1', '/etc/hosts')

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
    expect(postMock).toHaveBeenCalledWith('/backup/start', {
      repository: '/repo-v1',
      archive_name: 'nightly',
    })
    expect(postMock).toHaveBeenCalledWith('/repositories/7/prune', {
      keep_daily: 7,
      keep_within: '1d',
    })
    expect(postMock).toHaveBeenCalledWith('/repositories/7/compact')
    expect(postMock).toHaveBeenCalledWith('/repositories/7/check', { max_duration: 30 })
    expect(getMock).toHaveBeenCalledWith('/archives/download', {
      params: { repository: 7, archive: 'archive-1', file_path: '/etc/hosts' },
      responseType: 'blob',
    })
  })

  it('uses v2 routes for Borg 2 repositories', async () => {
    const clientModule = await import('./client')
    const getMock = vi.spyOn(clientModule.httpClient, 'get').mockResolvedValue({} as never)
    const postMock = vi.spyOn(clientModule.httpClient, 'post').mockResolvedValue({} as never)
    const { BorgApiClient } = clientModule
    const client = new BorgApiClient({ id: 9, borg_version: 2 } as never)

    client.runBackup({ archive_name: 'manual-v2' })
    client.getArchiveContents('archive-id', 'ignored-name', '/srv')
    client.pruneArchives({ keep_weekly: 4, keep_within: '1d' })
    client.compact()
    client.checkRepository()
    client.fetchArchiveFile('archive-2', '/srv/data.txt')

    expect(postMock).toHaveBeenCalledWith('/v2/backup/run', {
      repository_id: 9,
      archive_name: 'manual-v2',
    })
    expect(getMock).toHaveBeenCalledWith('/v2/archives/archive-id/contents', {
      params: { repository: 9, path: '/srv' },
    })
    expect(postMock).toHaveBeenCalledWith('/v2/backup/prune', {
      repository_id: 9,
      keep_weekly: 4,
      keep_within: '1d',
    })
    expect(postMock).toHaveBeenCalledWith('/v2/backup/compact', { repository_id: 9 })
    expect(postMock).toHaveBeenCalledWith('/v2/backup/check', {
      repository_id: 9,
    })
    expect(getMock).toHaveBeenCalledWith('/v2/archives/download', {
      params: { repository: 9, archive: 'archive-2', file_path: '/srv/data.txt' },
      responseType: 'blob',
    })
  })

  it('passes max_duration to Borg 2 check routes', async () => {
    const clientModule = await import('./client')
    const postMock = vi.spyOn(clientModule.httpClient, 'post').mockResolvedValue({} as never)
    const { BorgApiClient } = clientModule
    const client = new BorgApiClient({ id: 11, borg_version: 2 } as never)

    client.checkRepository(3600)

    expect(postMock).toHaveBeenCalledWith('/v2/backup/check', {
      repository_id: 11,
      max_duration: 3600,
    })
  })

  it('passes advanced check flags to Borg check routes', async () => {
    const clientModule = await import('./client')
    const postMock = vi.spyOn(clientModule.httpClient, 'post').mockResolvedValue({} as never)
    const { BorgApiClient } = clientModule
    const v1Client = new BorgApiClient({ id: 12, borg_version: 1 } as never)
    const v2Client = new BorgApiClient({ id: 13, borg_version: 2 } as never)

    v1Client.checkRepository({ maxDuration: 7200, checkExtraFlags: '--repair --save-space' })
    v2Client.checkRepository({ maxDuration: 0, checkExtraFlags: '--verify-data' })

    expect(postMock).toHaveBeenCalledWith('/repositories/12/check', {
      max_duration: 7200,
      check_extra_flags: '--repair --save-space',
    })
    expect(postMock).toHaveBeenCalledWith('/v2/backup/check', {
      repository_id: 13,
      max_duration: 0,
      check_extra_flags: '--verify-data',
    })
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
