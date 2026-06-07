import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearBackendAccessToken,
  clearLegacyRemoteBackendClients,
  createRemoteBackendClient,
  deleteRemoteBackendClient,
  getActiveBackendTarget,
  getBackendAccessToken,
  listRemoteBackendClients,
  LOCAL_BACKEND_ID,
  readRemoteBackendState,
  readLegacyRemoteBackendClients,
  replaceRemoteBackendClients,
  resetRemoteBackendStateForTests,
  setActiveBackendTarget,
  setBackendAccessToken,
  subscribeRemoteBackendStorage,
  updateRemoteBackendClient,
  updateRemoteBackendHealth,
} from './storage'

describe('remote client storage', () => {
  beforeEach(() => {
    localStorage.clear()
    resetRemoteBackendStateForTests()
  })

  it('defaults to this server when nothing is stored', () => {
    expect(readRemoteBackendState()).toEqual({
      activeTargetId: LOCAL_BACKEND_ID,
      clients: [],
    })

    expect(getActiveBackendTarget()).toMatchObject({
      id: LOCAL_BACKEND_ID,
      name: 'This server',
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
    expect(localStorage.getItem('borg_ui_remote_backends')).toBeNull()
  })

  it('keeps the remote client cache out of localStorage', () => {
    createRemoteBackendClient({
      name: 'Studio NAS',
      backendUrl: 'nas.local:9000',
    })

    expect(listRemoteBackendClients()).toHaveLength(1)
    expect(localStorage.getItem('borg_ui_remote_backends')).toBeNull()

    replaceRemoteBackendClients([])

    expect(listRemoteBackendClients()).toEqual([])
    expect(localStorage.getItem('borg_ui_remote_backends')).toBeNull()
  })

  it('returns defensive copies of cached remote clients', () => {
    const created = createRemoteBackendClient({
      name: 'Studio NAS',
      backendUrl: 'nas.local:9000',
    })

    const listed = listRemoteBackendClients()
    listed[0].name = 'Mutated NAS'
    listed[0].health.status = 'offline'

    expect(listRemoteBackendClients()[0]).toMatchObject({
      id: created.id,
      name: 'Studio NAS',
      health: {
        status: 'unknown',
      },
    })

    const state = readRemoteBackendState()
    state.clients[0].name = 'Mutated again'

    expect(readRemoteBackendState().clients[0].name).toBe('Studio NAS')
  })

  it('reads and clears legacy localStorage clients for admin migration', () => {
    const legacyClient = {
      id: 'legacy-client-1',
      kind: 'remote',
      name: 'Legacy NAS',
      apiBaseUrl: 'https://legacy.example.com/api',
      webBaseUrl: 'https://legacy.example.com',
      createdAt: '2026-06-05T00:00:00.000Z',
      updatedAt: '2026-06-05T00:00:00.000Z',
      health: {
        status: 'unknown',
        checkedAt: null,
        appVersion: null,
        borgVersion: null,
        borg2Version: null,
        error: null,
        compatibility: 'unknown',
        compatibilityMessage: null,
      },
    }
    localStorage.setItem('borg_ui_remote_backends', JSON.stringify([legacyClient]))

    expect(readLegacyRemoteBackendClients()).toEqual([legacyClient])

    clearLegacyRemoteBackendClients()

    expect(readLegacyRemoteBackendClients()).toEqual([])
    expect(localStorage.getItem('borg_ui_remote_backends')).toBeNull()
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

  it('restores the active remote target when the client cache has not hydrated yet', () => {
    const created = createRemoteBackendClient({
      name: 'Office server',
      backendUrl: 'https://office.example.com',
    })
    setActiveBackendTarget(created.id)

    replaceRemoteBackendClients([])

    expect(readRemoteBackendState().activeTargetId).toBe(created.id)
    expect(listRemoteBackendClients()).toEqual([])
    expect(getActiveBackendTarget()).toMatchObject({
      id: created.id,
      name: 'Office server',
      apiBaseUrl: 'https://office.example.com/api',
      kind: 'remote',
    })
    expect(() => setActiveBackendTarget(created.id)).not.toThrow()
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
    replaceRemoteBackendClients([])

    expect(listener).toHaveBeenCalledTimes(3)

    unsubscribe()
    createRemoteBackendClient({ name: 'Office', backendUrl: 'office.example.com' })
    expect(listener).toHaveBeenCalledTimes(3)
  })
})
