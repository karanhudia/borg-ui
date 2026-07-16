import { render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ActivityTimeline } from './ActivityTimeline'
import type { DashboardOverview } from './types'

type Activity = DashboardOverview['activity_feed'][number]

describe('ActivityTimeline', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('orders events within a day from oldest to newest when the feed is newest-first', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-16T12:00:00Z'))

    const activities: Activity[] = [
      {
        id: 3,
        type: 'backup',
        status: 'completed',
        repository: 'newest',
        timestamp: '2026-07-16T11:00:00Z',
        message: 'Newest backup',
        error: null,
      },
      {
        id: 2,
        type: 'backup',
        status: 'failed',
        repository: 'middle',
        timestamp: '2026-07-16T09:00:00Z',
        message: 'Middle backup',
        error: 'Connection refused',
      },
      {
        id: 1,
        type: 'backup',
        status: 'completed',
        repository: 'oldest',
        timestamp: '2026-07-16T07:00:00Z',
        message: 'Oldest backup',
        error: null,
      },
    ]

    const { container } = render(<ActivityTimeline activities={activities} />)

    expect(
      Array.from(container.querySelectorAll('circle title')).map(
        (title) => title.textContent?.split(' · ')[1]
      )
    ).toEqual(['oldest', 'middle', 'newest'])
  })
})
