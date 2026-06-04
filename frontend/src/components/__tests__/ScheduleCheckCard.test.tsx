import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen } from '../../test/test-utils'
import ScheduleCheckCard from '../ScheduleCheckCard'
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
  repository_id: 1,
  repository_name: 'My Repo',
  repository_path: '/backups/my-repo',
  check_cron_expression: '0 10 * * *',
  check_timezone: 'Asia/Kolkata',
  last_scheduled_check: null,
  next_scheduled_check: null,
  check_max_duration: 0,
  notify_on_check_success: false,
  notify_on_check_failure: true,
  enabled: true,
}

describe('ScheduleCheckCard', () => {
  beforeEach(() => {
    entityCardMock.mockClear()
  })

  it('shows the check schedule in its stored timezone intent', () => {
    renderWithProviders(
      <ScheduleCheckCard
        check={baseCheck}
        canManage
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onRunNow={vi.fn()}
        onToggle={vi.fn()}
      />
    )

    expect(screen.getByTestId('entity-card')).toBeInTheDocument()

    const expectedSchedule = formatCronHuman(baseCheck.check_cron_expression)
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
        stat.tooltip === `${baseCheck.check_cron_expression} (${baseCheck.check_timezone})`
    )

    expect(scheduleStat).toMatchObject({
      value: expectedSchedule,
      tooltip: `${baseCheck.check_cron_expression} (${baseCheck.check_timezone})`,
    })
    expect(scheduleStat?.tooltip).not.toBe(expectedSchedule)
    expect(props?.meta).toEqual(
      expect.arrayContaining([expect.objectContaining({ value: baseCheck.check_timezone })])
    )
  })

  it('shows next check in the schedule timezone', () => {
    const nextCheck = '2024-01-01T20:30:00Z'

    renderWithProviders(
      <ScheduleCheckCard
        check={{ ...baseCheck, next_scheduled_check: nextCheck }}
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
            label: string
            value: string
            tooltip?: { props?: { display?: { scheduledTimeZone?: string } } }
            color?: string
          }>
        }
      | undefined
    const nextCheckStat = props?.stats.find((stat) => stat.color === 'success')
    const expectedScheduleTime = new Date(nextCheck).toLocaleString(undefined, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZone: baseCheck.check_timezone,
    })

    expect(nextCheckStat).toMatchObject({
      value: expectedScheduleTime,
    })
    expect(nextCheckStat?.tooltip?.props?.display?.scheduledTimeZone).toBe(baseCheck.check_timezone)
  })

  it('surfaces configured advanced check flags in card metadata', () => {
    renderWithProviders(
      <ScheduleCheckCard
        check={{ ...baseCheck, check_extra_flags: '--verify-data' }}
        canManage
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onRunNow={vi.fn()}
        onToggle={vi.fn()}
      />
    )

    const props = entityCardMock.mock.lastCall?.[0] as
      | {
          meta: Array<{ label: string; value: string }>
        }
      | undefined

    expect(props?.meta).toEqual(
      expect.arrayContaining([expect.objectContaining({ value: '--verify-data' })])
    )
  })
})
