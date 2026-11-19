import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useSeasonalBadge } from '../useSeasonalBadge'

vi.mock('../useAnalytics', () => ({ useAnalytics: () => ({ trackAnnouncement: vi.fn() }) }))
vi.mock('../useSystemInfo', () => ({
  useSystemInfo: () => ({ data: { app_version: '2.5.0', plan: 'community' } }),
}))
vi.mock('../useAnnouncementsManifest', () => ({
  useAnnouncementsManifest: () => ({
    data: {
      version: 1,
      announcements: [
        {
          id: 'badge-test',
          type: 'seasonal_badge',
          emoji: '🛍️',
          title: 'Black Friday',
          message: 'Happy Black Friday.',
          cta_url: 'https://borgui.com/buy',
          cta_plans: ['community'],
          starts_at: '2026-11-23T00:00:00Z',
          ends_at: '2026-12-01T23:59:59Z',
        },
      ],
    },
  }),
}))

describe('useSeasonalBadge', () => {
  afterEach(() => vi.useRealTimers())

  it('drops the badge and sale link once the window ends, without a remount', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-12-01T23:59:30Z'))
    const { result } = renderHook(() => useSeasonalBadge())
    expect(result.current.badge?.id).toBe('badge-test')
    expect(result.current.showSale).toBe(true)

    act(() => vi.advanceTimersByTime(60_000))

    expect(result.current.badge).toBeNull()
    expect(result.current.showSale).toBe(false)
  })
})
