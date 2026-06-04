import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import BackupPlanRunsPanel from '../BackupPlanRunsPanel'
import type { BackupPlan, BackupPlanRun } from '../../types'

const plan = { id: 3, name: 'Nightly Plan' } as BackupPlan

describe('BackupPlanRunsPanel', () => {
  it('shows recent runs in a table and opens plan-level script logs from row actions', async () => {
    const user = userEvent.setup()
    const onViewLogs = vi.fn()
    const run = {
      id: 12,
      backup_plan_id: 3,
      trigger: 'manual',
      status: 'completed',
      started_at: '2026-05-11T10:00:00Z',
      completed_at: '2026-05-11T10:01:00Z',
      created_at: '2026-05-11T10:00:00Z',
      repositories: [],
      script_executions: [
        {
          id: 77,
          script_id: 5,
          script_name: 'Prepare Source',
          hook_type: 'pre-backup',
          status: 'completed',
          started_at: '2026-05-11T10:00:00Z',
          completed_at: '2026-05-11T10:00:01Z',
          execution_time: 1.23,
          exit_code: 0,
          has_logs: true,
        },
      ],
    } satisfies BackupPlanRun

    render(
      <BackupPlanRunsPanel runs={[run]} plans={[plan]} onCancel={vi.fn()} onViewLogs={onViewLogs} />
    )

    const recentSection = screen.getByRole('region', { name: /recent backup plan runs/i })
    expect(within(recentSection).getByRole('table')).toBeInTheDocument()
    expect(within(recentSection).getByText('#12')).toBeInTheDocument()
    expect(within(recentSection).getByText('Nightly Plan')).toBeInTheDocument()
    expect(within(recentSection).getByText('Completed')).toBeInTheDocument()

    await user.click(within(recentSection).getByRole('button', { name: /view logs/i }))

    expect(onViewLogs).toHaveBeenCalledWith({
      id: 77,
      status: 'completed',
      type: 'script_execution',
      has_logs: true,
    })
  })

  it('confirms and retries failed backup plan runs from recent history', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    const run = {
      id: 17,
      backup_plan_id: 3,
      trigger: 'manual',
      status: 'failed',
      started_at: '2026-05-11T10:00:00Z',
      completed_at: '2026-05-11T10:01:00Z',
      created_at: '2026-05-11T10:00:00Z',
      repositories: [
        {
          id: 97,
          repository_id: 7,
          status: 'failed',
          repository: {
            id: 7,
            name: 'Primary Repo',
            path: '/repos/primary',
          },
          backup_job: {
            id: 57,
            repository: '/repos/primary',
            repository_id: 7,
            status: 'failed',
          },
        },
      ],
    } satisfies BackupPlanRun

    render(
      <BackupPlanRunsPanel
        runs={[run]}
        plans={[plan]}
        onCancel={vi.fn()}
        onViewLogs={vi.fn()}
        onRetry={onRetry}
        canRetryRun={() => true}
      />
    )

    const recentSection = screen.getByRole('region', { name: /recent backup plan runs/i })
    await user.click(within(recentSection).getByRole('button', { name: /retry backup plan run/i }))

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Retry backup plan run #17?')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: /retry backup plan run/i }))

    expect(onRetry).toHaveBeenCalledWith(17)
  })

  it('does not show retry for cancelled backup plan runs', () => {
    const run = {
      id: 16,
      backup_plan_id: 3,
      trigger: 'manual',
      status: 'cancelled',
      started_at: '2026-05-11T10:00:00Z',
      completed_at: '2026-05-11T10:01:00Z',
      created_at: '2026-05-11T10:00:00Z',
      repositories: [
        {
          id: 96,
          repository_id: 7,
          status: 'cancelled',
          repository: {
            id: 7,
            name: 'Primary Repo',
            path: '/repos/primary',
          },
        },
      ],
    } satisfies BackupPlanRun

    render(
      <BackupPlanRunsPanel
        runs={[run]}
        plans={[plan]}
        onCancel={vi.fn()}
        onViewLogs={vi.fn()}
        onRetry={vi.fn()}
        canRetryRun={() => true}
      />
    )

    const recentSection = screen.getByRole('region', { name: /recent backup plan runs/i })
    expect(
      within(recentSection).queryByRole('button', { name: /retry backup plan run/i })
    ).not.toBeInTheDocument()
  })

  it('disables retry when a failed backup plan run has no failed repositories', () => {
    const run = {
      id: 18,
      backup_plan_id: 3,
      trigger: 'manual',
      status: 'failed',
      started_at: '2026-05-11T10:00:00Z',
      completed_at: '2026-05-11T10:01:00Z',
      created_at: '2026-05-11T10:00:00Z',
      repositories: [
        {
          id: 98,
          repository_id: 7,
          status: 'completed',
          repository: {
            id: 7,
            name: 'Primary Repo',
            path: '/repos/primary',
          },
          backup_job: {
            id: 58,
            repository: '/repos/primary',
            repository_id: 7,
            status: 'completed',
          },
        },
      ],
    } satisfies BackupPlanRun

    render(
      <BackupPlanRunsPanel
        runs={[run]}
        plans={[plan]}
        onCancel={vi.fn()}
        onViewLogs={vi.fn()}
        onRetry={vi.fn()}
        canRetryRun={() => true}
      />
    )

    expect(
      screen.getByRole('button', {
        name: /this run has no failed repositories to retry/i,
      })
    ).toBeDisabled()
  })

  it('disables retry while the same backup plan already has an active run', () => {
    const failedRun = {
      id: 19,
      backup_plan_id: 3,
      trigger: 'manual',
      status: 'failed',
      started_at: '2026-05-11T09:00:00Z',
      completed_at: '2026-05-11T09:01:00Z',
      repositories: [
        {
          id: 99,
          repository_id: 7,
          status: 'failed',
          repository: {
            id: 7,
            name: 'Primary Repo',
            path: '/repos/primary',
          },
          backup_job: {
            id: 59,
            repository: '/repos/primary',
            repository_id: 7,
            status: 'failed',
          },
        },
      ],
    } satisfies BackupPlanRun
    const activeRun = {
      id: 20,
      backup_plan_id: 3,
      trigger: 'manual',
      status: 'running',
      started_at: '2026-05-11T10:00:00Z',
      repositories: [
        {
          id: 100,
          repository_id: 7,
          status: 'running',
          repository: {
            id: 7,
            name: 'Primary Repo',
            path: '/repos/primary',
          },
        },
      ],
    } satisfies BackupPlanRun

    render(
      <BackupPlanRunsPanel
        runs={[failedRun, activeRun]}
        plans={[plan]}
        onCancel={vi.fn()}
        onViewLogs={vi.fn()}
        onRetry={vi.fn()}
        canRetryRun={() => true}
      />
    )

    const recentSection = screen.getByRole('region', { name: /recent backup plan runs/i })
    expect(
      within(recentSection).getByRole('button', {
        name: /wait for the running backup plan run to finish before retrying/i,
      })
    ).toBeDisabled()
  })

  it('keeps active plan runs separate from recent plan run history', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    const onViewLogs = vi.fn()
    const activeRun = {
      id: 13,
      backup_plan_id: 3,
      trigger: 'manual',
      status: 'running',
      started_at: '2026-05-11T10:00:00Z',
      repositories: [
        {
          id: 91,
          repository_id: 7,
          status: 'running',
          repository: {
            id: 7,
            name: 'Primary Repo',
            path: '/repos/primary',
          },
          backup_job: {
            id: 42,
            repository: '/repos/primary',
            repository_id: 7,
            status: 'running',
            has_logs: true,
          },
        },
      ],
    } satisfies BackupPlanRun
    const recentRun = {
      id: 12,
      backup_plan_id: 3,
      trigger: 'manual',
      status: 'completed',
      started_at: '2026-05-11T09:00:00Z',
      completed_at: '2026-05-11T09:01:00Z',
      repositories: [
        {
          id: 90,
          repository_id: 8,
          status: 'completed',
          repository: {
            id: 8,
            name: 'Archive Repo',
            path: '/repos/archive',
          },
          backup_job: {
            id: 41,
            repository: '/repos/archive',
            repository_id: 8,
            status: 'completed',
            has_logs: true,
          },
        },
      ],
    } satisfies BackupPlanRun

    render(
      <BackupPlanRunsPanel
        runs={[activeRun, recentRun]}
        plans={[plan]}
        onCancel={onCancel}
        onViewLogs={onViewLogs}
      />
    )

    const activeSection = screen.getByRole('region', { name: /running backup plan runs/i })
    const recentSection = screen.getByRole('region', { name: /recent backup plan runs/i })
    expect(within(activeSection).getByText('#13')).toBeInTheDocument()
    expect(within(activeSection).getByText('Primary Repo')).toBeInTheDocument()
    expect(within(activeSection).queryByText('#12')).not.toBeInTheDocument()
    expect(within(recentSection).getByText('#12')).toBeInTheDocument()
    expect(within(recentSection).getByText('Archive Repo')).toBeInTheDocument()
    expect(within(recentSection).queryByText('#13')).not.toBeInTheDocument()

    await user.click(within(activeSection).getByRole('button', { name: /view logs/i }))
    expect(onViewLogs).toHaveBeenCalledWith(expect.objectContaining({ id: 42 }))

    await user.click(within(activeSection).getByRole('button', { name: /cancel run/i }))
    expect(onCancel).toHaveBeenCalledWith(13)
  })

  it('opens logs for the currently running repository in an active plan run', async () => {
    const user = userEvent.setup()
    const onViewLogs = vi.fn()
    const activeRun = {
      id: 14,
      backup_plan_id: 3,
      trigger: 'manual',
      status: 'running',
      started_at: '2026-05-11T10:00:00Z',
      repositories: [
        {
          id: 92,
          repository_id: 8,
          status: 'completed',
          repository: {
            id: 8,
            name: 'Finished Repo',
            path: '/repos/finished',
          },
          backup_job: {
            id: 51,
            repository: '/repos/finished',
            repository_id: 8,
            status: 'completed',
            has_logs: true,
          },
        },
        {
          id: 93,
          repository_id: 9,
          status: 'running',
          repository: {
            id: 9,
            name: 'Running Repo',
            path: '/repos/running',
          },
          backup_job: {
            id: 52,
            repository: '/repos/running',
            repository_id: 9,
            status: 'running',
            has_logs: true,
          },
        },
      ],
    } satisfies BackupPlanRun

    render(
      <BackupPlanRunsPanel
        runs={[activeRun]}
        plans={[plan]}
        onCancel={vi.fn()}
        onViewLogs={onViewLogs}
      />
    )

    const activeSection = screen.getByRole('region', { name: /running backup plan runs/i })
    await user.click(within(activeSection).getByRole('button', { name: /view logs/i }))

    expect(onViewLogs).toHaveBeenCalledWith(expect.objectContaining({ id: 52 }))
  })

  it('shows transport context on repository rows', () => {
    const run = {
      id: 15,
      backup_plan_id: 3,
      trigger: 'manual',
      status: 'completed',
      started_at: '2026-05-11T10:00:00Z',
      completed_at: '2026-05-11T10:01:00Z',
      repositories: [
        {
          id: 94,
          repository_id: 10,
          status: 'completed',
          repository: {
            id: 10,
            name: 'Agent Repo',
            path: '/repos/agent',
            executor_type: 'agent',
          },
          backup_job: {
            id: 53,
            repository: '/repos/agent',
            repository_id: 10,
            status: 'completed',
            execution_mode: 'agent',
          },
        },
      ],
    } satisfies BackupPlanRun

    render(
      <BackupPlanRunsPanel runs={[run]} plans={[plan]} onCancel={vi.fn()} onViewLogs={vi.fn()} />
    )

    expect(screen.getByText('Agent')).toBeInTheDocument()
  })

  it('shows remote SSH transport for remote-direct repository rows', () => {
    const run = {
      id: 16,
      backup_plan_id: 3,
      trigger: 'manual',
      status: 'completed',
      started_at: '2026-05-11T10:00:00Z',
      completed_at: '2026-05-11T10:01:00Z',
      repositories: [
        {
          id: 95,
          repository_id: 11,
          status: 'completed',
          repository: {
            id: 11,
            name: 'Remote Repo',
            path: '/repos/remote',
            executor_type: 'server',
          },
          backup_job: {
            id: 54,
            repository: '/repos/remote',
            repository_id: 11,
            status: 'completed',
            execution_mode: 'remote_ssh',
            route_strategy: 'remote_direct',
          },
        },
      ],
    } satisfies BackupPlanRun

    render(
      <BackupPlanRunsPanel runs={[run]} plans={[plan]} onCancel={vi.fn()} onViewLogs={vi.fn()} />
    )

    expect(screen.getByText('Remote SSH')).toBeInTheDocument()
  })
})
