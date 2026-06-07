import { afterEach, describe, expect, it, vi } from 'vitest'

describe('buildDownloadUrl', () => {
  afterEach(() => {
    localStorage.clear()
    vi.resetModules()
  })

  it('omits token query parameter when no access token exists', async () => {
    const { buildDownloadUrl } = await import('../downloadUrl')

    const url = buildDownloadUrl('/archives/download', {
      repository: '/repo',
      archive: 'archive-1',
      file_path: '/etc/hosts',
    })

    expect(url).toContain('/api/archives/download?')
    expect(url).toContain('repository=%2Frepo')
    expect(url).toContain('archive=archive-1')
    expect(url).toContain('file_path=%2Fetc%2Fhosts')
    expect(url).not.toContain('token=')
  })

  it('appends token query parameter when an access token exists', async () => {
    localStorage.setItem('access_token', 'jwt-token')
    const { buildDownloadUrl } = await import('../downloadUrl')

    const url = buildDownloadUrl('/backup/logs/1/download')

    expect(url).toContain('/api/backup/logs/1/download?token=jwt-token')
  })

  it('uses the active remote backend API base and token', async () => {
    const {
      createRemoteBackendClient,
      setActiveBackendTarget,
      setBackendAccessToken,
      resetRemoteBackendStateForTests,
    } = await import('../../services/remoteBackends/storage')
    resetRemoteBackendStateForTests()
    const remote = createRemoteBackendClient({
      name: 'Remote NAS',
      backendUrl: 'https://nas.example.com/borg',
    })
    setActiveBackendTarget(remote.id)
    setBackendAccessToken('remote-token')
    const { buildDownloadUrl } = await import('../downloadUrl')

    const url = buildDownloadUrl('/archives/download', { repository: 7 })

    expect(url).toBe(
      'https://nas.example.com/borg/api/archives/download?repository=7&token=remote-token'
    )
  })
})
