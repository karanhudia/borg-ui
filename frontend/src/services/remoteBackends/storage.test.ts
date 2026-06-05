import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearBackendAccessToken,
  createRemoteBackendClient,
  deleteRemoteBackendClient,
  getActiveBackendTarget,
  getBackendAccessToken,
  listRemoteBackendClients,
  LOCAL_BACKEND_ID,
  readRemoteBackendState,
  resetRemoteBackendStateForTests,
  setActiveBackendTarget,
  setBackendAccessToken,
  subscribeRemoteBackendStorage,
  updateRemoteBackendClient,
  updateRemoteBackendHealth,
} from './storage'

describe('remote backend storage', () => {
  beforeEach(() => {
    localStorage.clear()
    resetRemoteBackendStateForTests()
  })

  it('defaults to the local backend when nothing is stored', () => {
    expect(readRemoteBackendState()).toEqual({
      activeTargetId: LOCAL_BACKEND_ID,
      clients: [],
    })

    expect(getActiveBackendTarget()).toMatchObject({
      id: LOCAL_BACKEND_ID,
      name: 'Local backend',
      kind: 'local',
      apiBaseUrl: '/api',
    })
  })

  it('creates, updates, lists, and deletes remote clients', () => {
    const created = createRemoteBackendClient({
      name: 'Studio NAS',
      backendUrl: 'nas.local:9000',
    })

    expect(created).toMatchObject({
      name: 'Studio NAS',
      apiBaseUrl: 'http://nas.local:9000/api',
      webBaseUrl: 'http://nas.local:9000',
      kind: 'remote',
    })

    const updated = updateRemoteBackendClient(created.id, {
      name: 'Studio NAS 2',
      backendUrl: 'https://nas.example.com/borg',
    })

    expect(updated).toMatchObject({
      id: created.id,
      name: 'Studio NAS 2',
      apiBaseUrl: 'https://nas.example.com/borg/api',
      webBaseUrl: 'https://nas.example.com/borg',
    })
    expect(listRemoteBackendClients()).toHaveLength(1)

    deleteRemoteBackendClient(created.id)

    expect(listRemoteBackendClients()).toEqual([])
    expect(getActiveBackendTarget().id).toBe(LOCAL_BACKEND_ID)
  })

  it('persists and switches the active remote target', () => {
    const created = createRemoteBackendClient({
      name: 'Office server',
      backendUrl: 'https://office.example.com',
    })

    setActiveBackendTarget(created.id)

    expect(getActiveBackendTarget()).toMatchObject({
      id: created.id,
      name: 'Office server',
      apiBaseUrl: 'https://office.example.com/api',
      kind: 'remote',
    })

    setActiveBackendTarget(LOCAL_BACKEND_ID)
    expect(getActiveBackendTarget().id).toBe(LOCAL_BACKEND_ID)
  })

  it('blocks activating an incompatible remote target', () => {
    const created = createRemoteBackendClient({
      name: 'Old server',
      backendUrl: 'https://old.example.com',
    })
    updateRemoteBackendHealth(created.id, {
      status: 'online',
      checkedAt: '2026-06-05T00:00:00.000Z',
      appVersion: '1.9.0',
      compatibility: 'incompatible',
      compatibilityMessage: 'Major version mismatch',
    })

    expect(() => setActiveBackendTarget(created.id)).toThrow('Major version mismatch')
    expect(getActiveBackendTarget().id).toBe(LOCAL_BACKEND_ID)
  })

  it('scopes JWT tokens by active backend while preserving the local key', () => {
    setBackendAccessToken('local-token')
    expect(localStorage.getItem('access_token')).toBe('local-token')
    expect(getBackendAccessToken()).toBe('local-token')

    const created = createRemoteBackendClient({
      name: 'Remote server',
      backendUrl: 'remote.example.com',
    })
    setActiveBackendTarget(created.id)

    expect(getBackendAccessToken()).toBeNull()
    setBackendAccessToken('remote-token')

    expect(localStorage.getItem('access_token')).toBe('local-token')
    expect(getBackendAccessToken()).toBe('remote-token')

    clearBackendAccessToken()
    expect(getBackendAccessToken()).toBeNull()

    setActiveBackendTarget(LOCAL_BACKEND_ID)
    expect(getBackendAccessToken()).toBe('local-token')
  })

  it('notifies same-tab subscribers when storage changes', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeRemoteBackendStorage(listener)

    createRemoteBackendClient({ name: 'Lab', backendUrl: 'lab.example.com' })
    setBackendAccessToken('token')

    expect(listener).toHaveBeenCalledTimes(2)

    unsubscribe()
    createRemoteBackendClient({ name: 'Office', backendUrl: 'office.example.com' })
    expect(listener).toHaveBeenCalledTimes(2)
  })
})
