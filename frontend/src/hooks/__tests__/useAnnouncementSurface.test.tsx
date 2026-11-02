import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useAnnouncementSurface } from '../useAnnouncementSurface'
import manifest from '../../data/announcements.json'

const mocks = vi.hoisted(() => ({
  systemInfo: {} as Record<string, unknown>,
  announcements: [] as unknown[],
  trackAnnouncement: vi.fn(),
}))
vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({
    data: { announcements: mocks.announcements },
    dataUpdatedAt: 1,
    errorUpdatedAt: 0,
  }),
}))
vi.mock('../useSystemInfo', () => ({ useSystemInfo: () => ({ data: mocks.systemInfo }) }))
vi.mock('../useAnalytics', () => ({
  useAnalytics: () => ({
    trackAnnouncement: mocks.trackAnnouncement,
    EventAction: { VIEW: 'View' },
  }),
}))

describe('useAnnouncementSurface runtime inputs', () => {
  beforeEach(() => {
    localStorage.clear()
    mocks.systemInfo = { app_version: '2.4.0', plan: 'community' }
    mocks.announcements = [
      {
        ...manifest.announcements[0],
        starts_at: undefined,
        ends_at: undefined,
        min_app_version: '2.0.0',
        max_app_version: '2.4.0',
      },
    ]
  })

  it('keeps login usable when system info has no app version', () => {
    mocks.systemInfo = { plan: 'community' }
    const { result } = renderHook(() => useAnnouncementSurface())
    expect(result.current.announcement).toBeNull()
  })

  it('ignores a malformed cached manifest envelope', () => {
    mocks.announcements = null as unknown as unknown[]
    const { result } = renderHook(() => useAnnouncementSurface())
    expect(result.current.announcement).toBeNull()
  })

  it('ignores malformed cached items while showing a valid announcement', () => {
    mocks.announcements.unshift(null, {}, false)
    const { result } = renderHook(() => useAnnouncementSurface())
    expect(result.current.announcement?.id).toBe(manifest.announcements[0].id)
  })
})

// The sidebar consumes the same announcement feed and version response after login.
describe('useUpdateNotice runtime inputs', () => {
  it('hides version notices when the installed version is missing', async () => {
    const { useUpdateNotice } = await import('../useUpdateNotice')
    mocks.systemInfo = { plan: 'community' }
    mocks.announcements = [manifest.announcements[0]]
    const { result } = renderHook(() => useUpdateNotice())
    expect(result.current.notice).toBeNull()
  })

  it('skips malformed cached items while preserving valid updates', async () => {
    const { useUpdateNotice } = await import('../useUpdateNotice')
    mocks.systemInfo = { app_version: '2.0.0', plan: 'community' }
    mocks.announcements = [null, {}, manifest.announcements[0]]
    const { result } = renderHook(() => useUpdateNotice())
    expect(result.current.notice?.id).toBe(manifest.announcements[0].id)
  })
})
