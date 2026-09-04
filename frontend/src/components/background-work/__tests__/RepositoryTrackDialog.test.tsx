import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import RepositoryTrackDialog from '../RepositoryTrackDialog'
import { archivesAPI } from '../../../services/api'
import type { OperationItem } from '../../../types/operations'

vi.mock('../../../services/api', () => ({
  archivesAPI: { rebuild: vi.fn().mockResolvedValue({ data: { run_id: 'r1', operations: [1] } }) },
}))

const op = (overrides: Partial<OperationItem>): OperationItem => ({
  activity_key: null,
  id: 1,
  type: 'operation',
  kind: 'stats',
  category: 'index',
  status: 'completed',
  trigger: 'reconcile',
  priority: 20,
  run_id: 'r1',
  depends_on_id: null,
  repository_id: 3,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: '2026-09-04T00:00:00Z',
  completed_at: '2026-09-04T00:01:00Z',
  created_at: '2026-09-04T00:00:00Z',
  error_message: null,
  skip_reason: null,
  log_file_path: null,
  triggered_by: 'reconcile',
  schedule_id: null,
  schedule_name: null,
  backup_plan_id: null,
  backup_plan_run_id: null,
  backup_plan_name: null,
  archive_name: null,
  package_name: null,
  has_logs: false,
  progress_percent: null,
  progress_current: null,
  progress_total: null,
  progress_message: null,
  execution_mode: null,
  params: null,
  result: null,
  followups: [],
  ...overrides,
})

describe('RepositoryTrackDialog', () => {
  it('renders one row per operation with its stage timing', () => {
    render(
      <RepositoryTrackDialog
        open
        onClose={vi.fn()}
        repositoryId={3}
        repositoryName="nas"
        operations={[op({ kind: 'stats' }), op({ id: 2, kind: 'archive_sync' })]}
      />
    )
    expect(screen.getByText('nas')).toBeInTheDocument()
  })

  it('triggers a rebuild for the selected stage', async () => {
    render(
      <RepositoryTrackDialog
        open
        onClose={vi.fn()}
        repositoryId={3}
        repositoryName="nas"
        operations={[op({})]}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /rebuild from/i }))
    await waitFor(() => expect(archivesAPI.rebuild).toHaveBeenCalledWith(3, 'stats'))
  })
})
