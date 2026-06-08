import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('auth fetch helpers', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    vi.resetModules()
  })

  it('fetches JSON from the active remote backend proxy with local and target auth', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const {
      createRemoteBackendClient,
      setActiveBackendTarget,
      setBackendAccessToken,
      resetRemoteBackendStateForTests,
    } = await import('./remoteBackends/storage')
    resetRemoteBackendStateForTests()
    const remote = createRemoteBackendClient({
      name: 'Lab',
      backendUrl: 'lab.example.com',
    })
    setBackendAccessToken('local-token')
    setActiveBackendTarget(remote.id)
    setBackendAccessToken('remote-token', remote.id)

    const { fetchJsonWithAuth } = await import('./authRequest')
    await fetchJsonWithAuth('/auth/me')

    expect(fetchMock).toHaveBeenCalledWith(`/api/remote-clients/${remote.id}/proxy/api/auth/me`, {
      headers: expect.any(Headers),
    })
    const headers = fetchMock.mock.calls[0][1].headers as Headers
    expect(headers.get('X-Borg-Authorization')).toBe('Bearer local-token')
    expect(headers.get('X-Borg-Remote-Authorization')).toBe('Bearer remote-token')
    expect(headers.get('Accept')).toBe('application/json')
  })
})
