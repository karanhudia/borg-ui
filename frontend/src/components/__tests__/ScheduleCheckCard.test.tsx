import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen } from '../../test/test-utils'
import ScheduleCheckCard from '../ScheduleCheckCard'
import { convertCronToLocal, formatCronHuman } from '../../utils/dateUtils'

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
  last_scheduled_check: null,
  next_scheduled_check: null,
  check_max_duration: 0,
  notify_on_check_success: false,
  notify_on_check_failure: true,
  enabled: true,
}

describe('ScheduleCheckCard', () => {
  it('uses the same local schedule text for the stat value and tooltip', () => {
    renderWithProviders(
      <ScheduleCheckCard
        check={baseCheck}
        canManage
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onRunNow={vi.fn()}
      />
    )

    expect(screen.getByTestId('entity-card')).toBeInTheDocument()

    const props = entityCardMock.mock.calls[0][0] as {
      stats: Array<{ label: string; value: string; tooltip?: string }>
    }
    const scheduleStat = props.stats.find((stat) => stat.label === 'Schedule')
    const expectedSchedule = formatCronHuman(convertCronToLocal(baseCheck.check_cron_expression))

    expect(scheduleStat).toMatchObject({
      value: expectedSchedule,
      tooltip: expectedSchedule,
    })
    expect(scheduleStat?.tooltip).not.toBe(baseCheck.check_cron_expression)
  })
})
