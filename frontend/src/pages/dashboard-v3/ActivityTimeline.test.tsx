import { render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ActivityTimeline } from './ActivityTimeline'
import { JOB_COLOR } from './tokens'
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

  it('maps restore_check events onto the restore lane', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-16T12:00:00Z'))

    const activities: Activity[] = [
      {
        id: 1,
        type: 'backup',
        status: 'completed',
        repository: 'repo',
        timestamp: '2026-07-16T07:00:00Z',
        message: 'Backup completed',
        error: null,
      },
      {
        id: 2,
        type: 'restore_check',
        status: 'completed',
        repository: 'repo',
        timestamp: '2026-07-16T08:00:00Z',
        message: 'Restore check completed',
        error: null,
      },
    ]

    const { container } = render(<ActivityTimeline activities={activities} />)

    const titles = Array.from(container.querySelectorAll('circle title'))
    const restoreDot = titles.find((title) => title.textContent?.startsWith('restore_check'))
    const backupDot = titles.find((title) => title.textContent?.startsWith('backup'))
    expect(restoreDot).toBeDefined()
    expect(backupDot).toBeDefined()

    // The restore lane is 3 lanes below the backup lane, in the restore color.
    const cyOf = (title: Element) => Number(title.closest('circle')?.getAttribute('cy'))
    const laneHeight = 14
    expect(cyOf(restoreDot!)).toBe(cyOf(backupDot!) + 3 * laneHeight)
    expect(restoreDot!.closest('circle')?.getAttribute('fill')).toBe(JOB_COLOR.restore)
  })
})
