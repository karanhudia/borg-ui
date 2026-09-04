import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import PipelineRepositoryCard from '../PipelineRepositoryCard'
import type { OperationItem } from '../../../types/operations'

const baseOp: OperationItem = {
  activity_key: null,
  id: 1,
  type: 'operation',
  kind: 'archive_sync',
  category: 'index',
  status: 'running',
  trigger: 'reconcile',
  priority: 20,
  run_id: 'r1',
  depends_on_id: null,
  repository_id: 5,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: '2026-09-04T00:00:00Z',
  completed_at: null,
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
  progress_percent: 40,
  progress_current: 14,
  progress_total: 38,
  progress_message: null,
  execution_mode: null,
  params: null,
  result: null,
  followups: [],
}

describe('PipelineRepositoryCard', () => {
  it('shows the repository name and a progress bar while running', () => {
    render(<PipelineRepositoryCard operation={baseOp} />)
    expect(screen.getByText('nas')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('shows a retry action for a failed operation and calls onRetry', () => {
    const onRetry = vi.fn()
    render(
      <PipelineRepositoryCard
        operation={{ ...baseOp, status: 'failed', progress_percent: null }}
        onRetry={onRetry}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledWith(1)
  })

  it('renders no retry action for a running operation', () => {
    render(<PipelineRepositoryCard operation={baseOp} onRetry={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument()
  })
})
