import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen } from '../../test/test-utils'
import ScheduleJobCard from '../ScheduleJobCard'
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

const baseJob = {
  id: 1,
  name: 'Daily Backup',
  cron_expression: '0 10 * * *',
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
  it('uses the same local schedule text for the stat value and tooltip', () => {
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

    const props = entityCardMock.mock.calls[0][0] as {
      stats: Array<{ label: string; value: string; tooltip?: string }>
    }
    const scheduleStat = props.stats.find((stat) => stat.label === 'Schedule')
    const expectedSchedule = formatCronHuman(convertCronToLocal(baseJob.cron_expression))

    expect(scheduleStat).toMatchObject({
      value: expectedSchedule,
      tooltip: expectedSchedule,
    })
    expect(scheduleStat?.tooltip).not.toBe(baseJob.cron_expression)
  })
})
