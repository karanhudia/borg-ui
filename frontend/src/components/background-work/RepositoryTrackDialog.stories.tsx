import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'
import { Button } from '@mui/material'
import RepositoryTrackDialog from './RepositoryTrackDialog'
import type { OperationItem } from '../../types/operations'

const op = (overrides: Partial<OperationItem>): OperationItem => ({
  activity_key: null,
  id: overrides.id ?? 1,
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

const meta = {
  title: 'BackgroundWork/RepositoryTrackDialog',
} satisfies Meta<typeof RepositoryTrackDialog>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => {
    const Wrapper = () => {
      const [open, setOpen] = useState(true)
      return (
        <>
          <Button onClick={() => setOpen(true)}>Open</Button>
          <RepositoryTrackDialog
            open={open}
            onClose={() => setOpen(false)}
            repositoryId={3}
            repositoryName="nas"
            operations={[
              op({ kind: 'stats' }),
              op({ id: 2, kind: 'archive_sync', status: 'running' }),
            ]}
          />
        </>
      )
    }
    return <Wrapper />
  },
}
