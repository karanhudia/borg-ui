import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { TFunction } from 'i18next'
import { describe, expect, it, vi } from 'vitest'

import type { BackupPlanRun } from '../../../../types'
import { PlanRunsHistoryTable } from '../PlanRunsHistoryTable'

// The component takes `t` as a prop; the shared script section uses the global
// i18n instance, so raw values (script names) render regardless.
const t = ((key: string, opts?: { defaultValue?: string }) =>
  opts?.defaultValue ?? key) as unknown as TFunction

function makeRun(overrides: Partial<BackupPlanRun> = {}): BackupPlanRun {
  return {
    id: 571,
    backup_plan_id: 3,
    trigger: 'manual',
    status: 'completed',
    started_at: '2026-07-09T10:44:00Z',
    completed_at: '2026-07-09T10:49:49Z',
    created_at: '2026-07-09T10:44:00Z',
    repositories: [],
    script_executions: [
      {
        id: 3,
        script_id: null,
        script_name: 'backup-cluster-mariadb',
        hook_type: 'pre-backup',
        status: 'completed',
        started_at: '2026-07-09T10:48:39Z',
        completed_at: '2026-07-09T10:48:41Z',
        execution_time: 2.1,
        exit_code: 0,
        has_logs: true,
      },
    ],
    ...overrides,
  } as BackupPlanRun
}

describe('PlanRunsHistoryTable', () => {
  it('reveals a run’s script executions when its row is expanded', async () => {
    const user = userEvent.setup()
    const onViewLogs = vi.fn()

    render(
      <PlanRunsHistoryTable
        runs={[makeRun()]}
        cancelling={null}
        onViewLogs={onViewLogs}
        onCancel={vi.fn()}
        t={t}
      />
    )

    // Collapsed by default: the script row is not mounted.
    expect(screen.queryByText(/backup-cluster-mariadb/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /show scripts/i }))

    const scriptRow = await screen.findByText(/backup-cluster-mariadb/)
    expect(scriptRow).toBeInTheDocument()

    // Two "view logs" affordances must be present: the row-level eye and the
    // expanded script row's own button. Asserting the count guards against the
    // script-row button silently not rendering (which would leave only the eye).
    const viewLogsButtons = screen.getAllByRole('button', { name: /view logs/i })
    expect(viewLogsButtons).toHaveLength(2)
    // Click the in-row (script) button — the last one in DOM order.
    await user.click(viewLogsButtons[viewLogsButtons.length - 1])
    expect(onViewLogs).toHaveBeenCalledWith({
      id: 3,
      status: 'completed',
      type: 'script_execution',
      has_logs: true,
    })
  })

  it('opens the borg backup job — not a pre-backup script — from the run-level eye', async () => {
    const user = userEvent.setup()
    const onViewLogs = vi.fn()

    // A completed run whose pre-backup script (mariadb) AND borg job both have
    // viewable logs. The row-level eye must open the borg job; the script has
    // its own button inside the expanded section.
    const run = makeRun({
      repositories: [
        {
          id: 91,
          repository_id: 7,
          status: 'completed',
          backup_job: {
            id: 640,
            repository: '/repos/primary',
            repository_id: 7,
            status: 'completed',
            has_logs: true,
          },
        },
      ],
    })

    render(
      <PlanRunsHistoryTable
        runs={[run]}
        cancelling={null}
        onViewLogs={onViewLogs}
        onCancel={vi.fn()}
        t={t}
      />
    )

    // Collapsed: the only "view logs" affordance is the row-level eye.
    await user.click(screen.getByRole('button', { name: /view logs/i }))

    expect(onViewLogs).toHaveBeenCalledWith(
      expect.objectContaining({ id: 640, status: 'completed' })
    )
    expect(onViewLogs).not.toHaveBeenCalledWith(
      expect.objectContaining({ type: 'script_execution' })
    )
  })

  it('shows no expand control for runs without script executions', () => {
    render(
      <PlanRunsHistoryTable
        runs={[makeRun({ script_executions: [] })]}
        cancelling={null}
        onViewLogs={vi.fn()}
        onCancel={vi.fn()}
        t={t}
      />
    )

    expect(screen.queryByRole('button', { name: /show scripts/i })).not.toBeInTheDocument()
  })
})
