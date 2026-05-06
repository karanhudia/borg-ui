import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen } from '../../test/test-utils'
import ScheduleJobCard from '../ScheduleJobCard'
import { formatCronHuman } from '../../utils/dateUtils'

const { entityCardMock } = vi.hoisted(() => ({
  entityCardMock: vi.fn(),
}))

vi.mock('../EntityCard', () => ({
  default: (props: unknown) => {
    entityCardMock(props)
    return <div data-testid="entity-card" />
  },
}))

const baseJob = {
  id: 1,
  name: 'Daily Backup',
  cron_expression: '0 10 * * *',
  timezone: 'Asia/Kolkata',
  repository: null,
  repository_id: 1,
  repository_ids: null,
  enabled: true,
  last_run: null,
  next_run: null,
  description: 'Daily backup job',
  run_prune_after: false,
  run_compact_after: false,
  prune_keep_hourly: 0,
  prune_keep_daily: 7,
  prune_keep_weekly: 4,
  prune_keep_monthly: 6,
  prune_keep_quarterly: 0,
  prune_keep_yearly: 1,
  last_prune: null,
  last_compact: null,
}

describe('ScheduleJobCard', () => {
  beforeEach(() => {
    entityCardMock.mockClear()
  })

  it('shows the schedule in its stored timezone intent', () => {
    renderWithProviders(
      <ScheduleJobCard
        job={baseJob}
        repositories={[{ id: 1, name: 'My Repo', path: '/backups/my-repo' }]}
        canManage
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onDuplicate={vi.fn()}
        onRunNow={vi.fn()}
        onToggle={vi.fn()}
      />
    )

    expect(screen.getByTestId('entity-card')).toBeInTheDocument()

    const expectedSchedule = formatCronHuman(baseJob.cron_expression)
    const props = entityCardMock.mock.lastCall?.[0] as
      | {
          stats: Array<{ label: string; value: string; tooltip?: string }>
          meta: Array<{ label: string; value: string }>
        }
      | undefined
    expect(props).toBeDefined()
    const scheduleStat = props?.stats.find(
      (stat) =>
        stat.value === expectedSchedule &&
        stat.tooltip === `${baseJob.cron_expression} (${baseJob.timezone})`
    )

    expect(scheduleStat).toMatchObject({
      value: expectedSchedule,
      tooltip: `${baseJob.cron_expression} (${baseJob.timezone})`,
    })
    expect(scheduleStat?.tooltip).not.toBe(expectedSchedule)
    expect(props?.meta).toEqual(
      expect.arrayContaining([expect.objectContaining({ value: baseJob.timezone })])
    )
  })

  it('shows next run in the schedule timezone', () => {
    const nextRun = '2024-01-01T20:30:00Z'

    renderWithProviders(
      <ScheduleJobCard
        job={{ ...baseJob, next_run: nextRun }}
        repositories={[{ id: 1, name: 'My Repo', path: '/backups/my-repo' }]}
        canManage
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onDuplicate={vi.fn()}
        onRunNow={vi.fn()}
        onToggle={vi.fn()}
      />
    )

    const props = entityCardMock.mock.lastCall?.[0] as
      | {
          stats: Array<{
            label: string
            value: string
            tooltip?: { props?: { display?: { scheduledTimeZone?: string } } }
            color?: string
          }>
        }
      | undefined
    const nextRunStat = props?.stats.find((stat) => stat.color === 'success')
    const expectedScheduleTime = new Date(nextRun).toLocaleString(undefined, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZone: baseJob.timezone,
    })

    expect(nextRunStat).toMatchObject({
      value: expectedScheduleTime,
    })
    expect(nextRunStat?.tooltip?.props?.display?.scheduledTimeZone).toBe(baseJob.timezone)
  })
})
