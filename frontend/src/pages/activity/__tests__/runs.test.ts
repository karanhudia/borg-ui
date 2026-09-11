import { describe, it, expect } from 'vitest'
import i18n from '../../../i18n'
import type { ActivityItem } from '../../Activity'
import {
  clusterRuns,
  flattenRuns,
  groupByDay,
  repositoryCount,
  runChain,
  runTitle,
  umbrella,
} from '../runs'

const t = i18n.t.bind(i18n)

const item = (overrides: Partial<ActivityItem>): ActivityItem => ({
  id: 1,
  type: 'backup',
  kind: 'backup',
  category: 'backup',
  status: 'completed',
  started_at: '2026-09-11T08:30:12Z',
  completed_at: '2026-09-11T08:32:24Z',
  error_message: null,
  repository: 'nas',
  repository_id: 1,
  repository_path: '/mnt/nas',
  log_file_path: null,
  archive_name: null,
  package_name: null,
  ...overrides,
})

describe('umbrella', () => {
  it('names the plan a plan run belongs to', () => {
    expect(umbrella(item({ trigger: 'plan', backup_plan_name: 'Nightly' }), t)).toEqual({
      kind: 'plan',
      label: 'Plan · Nightly',
    })
  })

  it('names the schedule a scheduled run belongs to', () => {
    expect(umbrella(item({ trigger: 'schedule', schedule_name: 'Weekly' }), t).label).toBe(
      'Schedule · Weekly'
    )
  })

  it('falls back to the trigger when the umbrella has no name', () => {
    expect(umbrella(item({ trigger: 'plan' }), t).label).toBe('Plan')
    expect(umbrella(item({ trigger: 'reconcile' }), t)).toEqual({
      kind: 'reconcile',
      label: 'Reconcile',
    })
  })

  it('reads legacy rows from triggered_by', () => {
    expect(
      umbrella(item({ trigger: null, triggered_by: 'backup_plan', backup_plan_name: 'Docs' }), t)
        .label
    ).toBe('Plan · Docs')
    expect(umbrella(item({ trigger: null, triggered_by: 'schedule' }), t).kind).toBe('schedule')
    expect(umbrella(item({ trigger: null, triggered_by: 'initial' }), t)).toEqual({
      kind: 'other',
      label: 'Initial',
    })
  })
})

describe('runTitle', () => {
  it('uses the job type labels the table used', () => {
    expect(runTitle(item({ type: 'restore_check', kind: 'restore_check' }), t)).toBe(
      'Restore Check'
    )
    expect(runTitle(item({ type: 'script_execution', kind: null }), t)).toBe('Script')
  })

  it('names an index run after what started it and lists itself first', () => {
    const run = item({
      type: 'archive_sync',
      kind: 'archive_sync',
      category: 'index',
      trigger: 'reconcile',
      followups: [item({ id: 2, type: 'stats', kind: 'stats', category: 'index' })],
    })
    expect(runTitle(run, t)).toBe('Reconcile run')
    expect(runChain(run).followups?.map((step) => step.kind)).toEqual(['archive_sync', 'stats'])
  })

  it('capitalises operation kinds without a legacy label', () => {
    expect(runTitle(item({ type: 'delete_archive', kind: 'delete_archive' }), t)).toBe(
      'Delete archive'
    )
  })
})

describe('groupByDay', () => {
  it('groups runs by calendar day, newest day first', () => {
    const groups = groupByDay([
      item({ id: 1, started_at: '2026-09-10T08:00:00Z', completed_at: null }),
      item({ id: 2, started_at: '2026-09-11T08:00:00Z', completed_at: null }),
      item({ id: 3, started_at: '2026-09-11T09:00:00Z', completed_at: null }),
    ])
    expect(groups.map((group) => group.items.map((run) => run.id))).toEqual([[2, 3], [1]])
  })
})

describe('repositoryCount', () => {
  it('counts distinct repositories', () => {
    expect(
      repositoryCount([
        item({ repository_id: 1 }),
        item({ repository_id: 1 }),
        item({ repository_id: 2 }),
        item({ repository_id: null, repository_path: null, repository: null }),
      ])
    ).toBe(2)
  })
})

describe('clusterRuns', () => {
  it('keeps legacy schedules apart by name when they carry no schedule id', () => {
    const clusters = clusterRuns(
      [
        item({ id: 1, trigger: 'schedule', schedule_name: 'Weekly' }),
        item({ id: 2, trigger: 'schedule', schedule_name: 'Nightly' }),
        item({ id: 3, trigger: 'schedule', schedule_name: 'Weekly' }),
      ],
      t
    )
    expect(clusters.map((cluster) => cluster.items.map((run) => run.id))).toEqual([[1, 3], [2]])
  })

  it('does not merge a schedule id with a legacy schedule name that spells the same', () => {
    const clusters = clusterRuns(
      [
        item({ id: 1, trigger: 'schedule', schedule_id: 7, schedule_name: 'Weekly' }),
        item({ id: 2, trigger: 'schedule', schedule_name: '7' }),
      ],
      t
    )
    expect(clusters).toHaveLength(2)
  })

  it('does not fold a schedule into another whose name it prefixes, in either order', () => {
    const runs = [
      item({ id: 1, trigger: 'schedule', schedule_name: 'weekly-prod' }),
      item({ id: 2, trigger: 'schedule', schedule_name: 'weekly' }),
    ]
    expect(clusterRuns(runs, t)).toHaveLength(2)
    expect(clusterRuns([...runs].reverse(), t)).toHaveLength(2)
  })
})

describe('flattenRuns', () => {
  it('lists each run followed by its steps', () => {
    const steps = flattenRuns([item({ id: 1, followups: [item({ id: 11 }), item({ id: 12 })] })])
    expect(steps.map((run) => run.id)).toEqual([1, 11, 12])
  })
})
