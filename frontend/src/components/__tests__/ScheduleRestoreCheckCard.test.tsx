import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen } from '../../test/test-utils'
import ScheduleRestoreCheckCard from '../ScheduleRestoreCheckCard'
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

const baseCheck = {
  repository_id: 7,
  repository_name: 'Archive Repo',
  repository_path: '/backups/archive-repo',
  restore_check_cron_expression: '0 4 * * 0',
  restore_check_timezone: 'Asia/Kolkata',
  restore_check_paths: ['/etc/hostname', '/srv/app/config.yml'],
  restore_check_full_archive: false,
  restore_check_mode: 'probe_paths' as const,
  last_restore_check: null,
  last_scheduled_restore_check: null,
  next_scheduled_restore_check: null,
  notify_on_restore_check_success: false,
  notify_on_restore_check_failure: true,
  enabled: true,
}

describe('ScheduleRestoreCheckCard', () => {
  beforeEach(() => {
    entityCardMock.mockClear()
  })

  it('shows the restore-check schedule in its stored timezone intent', () => {
    renderWithProviders(
      <ScheduleRestoreCheckCard
        check={baseCheck}
        canManage
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onRunNow={vi.fn()}
        onToggle={vi.fn()}
      />
    )

    expect(screen.getByTestId('entity-card')).toBeInTheDocument()

    const expectedSchedule = formatCronHuman(baseCheck.restore_check_cron_expression)
    const props = entityCardMock.mock.lastCall?.[0] as
      | {
          stats: Array<{ label: string; value: string; tooltip?: string }>
          meta: Array<{ label: string; value: string }>
        }
      | undefined

    const scheduleStat = props?.stats.find(
      (stat) =>
        stat.value === expectedSchedule &&
        stat.tooltip ===
          `${baseCheck.restore_check_cron_expression} (${baseCheck.restore_check_timezone})`
    )
    expect(scheduleStat).toMatchObject({
      value: expectedSchedule,
      tooltip: `${baseCheck.restore_check_cron_expression} (${baseCheck.restore_check_timezone})`,
    })
    expect(props?.meta).toEqual(
      expect.arrayContaining([expect.objectContaining({ value: baseCheck.restore_check_timezone })])
    )
  })

  it('shows next restore check in the schedule timezone', () => {
    const nextRun = '2024-01-01T22:30:00Z'

    renderWithProviders(
      <ScheduleRestoreCheckCard
        check={{ ...baseCheck, next_scheduled_restore_check: nextRun }}
        canManage
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onRunNow={vi.fn()}
        onToggle={vi.fn()}
      />
    )

    const props = entityCardMock.mock.lastCall?.[0] as
      | {
          stats: Array<{
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
      timeZone: baseCheck.restore_check_timezone,
    })

    expect(nextRunStat).toMatchObject({
      value: expectedScheduleTime,
    })
    expect(nextRunStat?.tooltip?.props?.display?.scheduledTimeZone).toBe(
      baseCheck.restore_check_timezone
    )
  })
})
