import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import PipelineStageColumn from '../PipelineStageColumn'
import type { OperationItem } from '../../../types/operations'

const op = (overrides: Partial<OperationItem>): OperationItem => ({
  activity_key: null,
  id: overrides.id ?? 1,
  type: 'operation',
  kind: 'stats',
  category: 'index',
  status: 'queued',
  trigger: 'reconcile',
  priority: 20,
  run_id: 'r1',
  depends_on_id: null,
  repository_id: 1,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: null,
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

describe('PipelineStageColumn', () => {
  it('shows the stage label and operation count', () => {
    render(
      <PipelineStageColumn
        stage={{ key: 'stats', label: 'Stats', operations: [op({}), op({ id: 2 })] }}
      />
    )
    expect(screen.getByText('Stats')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('renders a card per operation', () => {
    render(
      <PipelineStageColumn
        stage={{ key: 'stats', label: 'Stats', operations: [op({}), op({ id: 2 })] }}
      />
    )
    expect(screen.getAllByText('nas')).toHaveLength(2)
  })

  it('renders the worker control when provided', () => {
    render(
      <PipelineStageColumn
        stage={{ key: 'history_index', label: 'History index', operations: [] }}
        workerControl={<span>workers: index 2</span>}
      />
    )
    expect(screen.getByText('workers: index 2')).toBeInTheDocument()
  })
})
