import { render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ActivityTimeline } from './ActivityTimeline'
import { JOB_COLOR } from './tokens'
import type { DashboardOverview } from './types'

type Timeline = NonNullable<DashboardOverview['activity_timeline']>

const FAILED_RING_RADIUS = '5.5'

function dotsOf(container: HTMLElement) {
  return Array.from(container.querySelectorAll('circle')).filter(
    (circle) => circle.getAttribute('r') !== FAILED_RING_RADIUS
  )
}

describe('ActivityTimeline', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('caps the dots of a busy day and names the real counts in the title', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-16T12:00:00'))

    const timeline: Timeline = [{ date: '2026-07-16', type: 'backup', total: 12, failed: 2 }]

    const { container } = render(<ActivityTimeline timeline={timeline} />)

    const dots = dotsOf(container)
    expect(dots).toHaveLength(5)
    expect(container.querySelectorAll(`circle[r="${FAILED_RING_RADIUS}"]`)).toHaveLength(2)
    expect(dots[0].querySelector('title')?.textContent).toBe('backup: 12 runs, 2 failed')
    // the failed runs take the rightmost dots
    const failedX = dots
      .filter((dot) => dot.getAttribute('fill') !== JOB_COLOR.backup)
      .map((dot) => Number(dot.getAttribute('cx')))
    const okX = dots
      .filter((dot) => dot.getAttribute('fill') === JOB_COLOR.backup)
      .map((dot) => Number(dot.getAttribute('cx')))
    expect(failedX).toHaveLength(2)
    expect(Math.min(...failedX)).toBeGreaterThan(Math.max(...okX))
  })

  it('drops a day outside the window and folds a day ahead into today', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-16T12:00:00'))

    const timeline: Timeline = [
      { date: '2026-07-10', type: 'check', total: 1, failed: 0 },
      { date: '2026-07-01', type: 'check', total: 4, failed: 4 },
      // dated today and tomorrow: the server bucketed in UTC for a viewer
      // west of it; both land in the today column as one cell
      { date: '2026-07-16', type: 'prune', total: 1, failed: 0 },
      { date: '2026-07-17', type: 'prune', total: 2, failed: 1 },
    ]

    const { container } = render(<ActivityTimeline timeline={timeline} />)

    const dots = dotsOf(container)
    expect(dots).toHaveLength(4)
    expect(dots[0].querySelector('title')?.textContent).toBe('check: 1 run, 0 failed')
    expect(dots[1].querySelector('title')?.textContent).toBe('prune: 3 runs, 1 failed')
    // the viewBox is 680 wide with 44 px of lane labels and 8 px of margin,
    // 14 columns: the last column's center
    const todayX = 44 + 13.5 * ((680 - 44 - 8) / 14)
    const todayDots = dots.slice(1).map((dot) => Number(dot.getAttribute('cx')))
    expect(Math.min(...todayDots)).toBeGreaterThan(todayX - 8)
    expect(Math.max(...todayDots)).toBeLessThan(todayX + 8)
  })

  it('maps restore_check counts onto the restore lane', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-16T12:00:00'))

    const timeline: Timeline = [
      { date: '2026-07-16', type: 'backup', total: 1, failed: 0 },
      { date: '2026-07-16', type: 'restore_check', total: 1, failed: 0 },
    ]

    const { container } = render(<ActivityTimeline timeline={timeline} />)

    const titles = Array.from(container.querySelectorAll('circle title'))
    const restoreDot = titles.find((title) => title.textContent?.startsWith('restore check'))
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
