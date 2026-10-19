import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ActiveBackupPlanRunCard from '../ActiveBackupPlanRunCard'
import type { BackupJob, BackupPlan, BackupPlanRun } from '../../types'

const plan: BackupPlan = {
  id: 1,
  name: 'Nightly',
  enabled: true,
  source_type: 'local',
  source_directories: ['/srv'],
  exclude_patterns: [],
  archive_name_template: '{hostname}-{now}',
  compression: 'zstd',
  repository_run_mode: 'series',
  max_parallel_repositories: 1,
  failure_behavior: 'stop',
  schedule_enabled: false,
  timezone: 'UTC',
  repository_count: 1,
}

function runWithProgress(
  progress_details: NonNullable<BackupJob['progress_details']>
): BackupPlanRun {
  return {
    id: 10,
    backup_plan_id: plan.id,
    trigger: 'manual',
    status: 'running',
    started_at: '2026-09-30T02:00:00Z',
    created_at: '2026-09-30T02:00:00Z',
    repositories: [
      {
        id: 20,
        repository_id: 30,
        status: 'running',
        repository: { id: 30, name: 'Repo', path: '/backups/repo', borg_version: 2 },
        backup_job: {
          id: 40,
          repository_id: 30,
          repository: '/backups/repo',
          type: 'backup',
          status: 'running',
          started_at: '2026-09-30T02:01:00Z',
          has_logs: true,
          progress_details,
        },
      },
    ],
    script_executions: [],
  }
}

const noop = () => {}

describe('ActiveBackupPlanRunCard progress row', () => {
  it('shows the formatted total source size after the label when the total is known', () => {
    render(
      <ActiveBackupPlanRunCard
        run={runWithProgress({
          original_size: 148_707_246_080,
          total_expected_size: 232_000_000_000,
          nfiles: 12_004,
          current_file: '/srv/ledger.sqlite',
        })}
        plan={plan}
        onCancel={noop}
        onViewLogs={noop}
      />
    )

    expect(screen.getByText('64.1%')).toBeInTheDocument()
    expect(screen.getByText(/Total Source Size:\s*216.07 GB/)).toBeInTheDocument()
  })

  it('hides the label when the total is unknown', () => {
    render(
      <ActiveBackupPlanRunCard
        run={runWithProgress({
          original_size: 8_100_000_000,
          nfiles: 100,
          current_file: '/srv/ledger.sqlite',
        })}
        plan={plan}
        onCancel={noop}
        onViewLogs={noop}
      />
    )

    expect(screen.queryByText(/Total Source Size/)).not.toBeInTheDocument()
  })

  it('leaves a repository without a total out of the proportion', () => {
    // A server repository with a total next to an agent repository without one:
    // the agent's bytes read must not count against the other's total.
    const run = runWithProgress({
      original_size: 50_000_000_000,
      total_expected_size: 100_000_000_000,
      nfiles: 10,
      current_file: '/srv/a',
    })
    const [known] = run.repositories
    run.repositories.push({
      ...known,
      id: 21,
      repository_id: 31,
      repository: { id: 31, name: 'Agent repo', path: '/backups/agent', borg_version: 2 },
      backup_job: {
        ...known.backup_job!,
        id: 41,
        repository_id: 31,
        repository: '/backups/agent',
        execution_mode: 'agent',
        progress: null,
        progress_details: {
          original_size: 40_000_000_000,
          total_expected_size: 0,
          nfiles: 5,
          current_file: '/srv/b',
        },
      },
    })

    render(<ActiveBackupPlanRunCard run={run} plan={plan} onCancel={noop} onViewLogs={noop} />)

    expect(screen.getByText('50.0%')).toBeInTheDocument()
  })
})
