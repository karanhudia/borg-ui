import type { Meta, StoryObj } from '@storybook/react-vite'
import { MemoryRouter } from 'react-router-dom'
import { Box } from '@mui/material'
import ForegroundLaneRow from './ForegroundLaneRow'
import type { OperationItem } from '../../types/operations'

const op: OperationItem = {
  activity_key: null,
  id: 1,
  type: 'operation',
  kind: 'backup',
  category: 'backup',
  status: 'running',
  trigger: 'schedule',
  priority: 5,
  run_id: 'r1',
  depends_on_id: null,
  repository_id: 7,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: new Date(Date.now() - 41 * 60 * 1000).toISOString(),
  completed_at: null,
  created_at: new Date().toISOString(),
  error_message: null,
  skip_reason: null,
  log_file_path: null,
  triggered_by: 'schedule',
  schedule_id: null,
  schedule_name: 'nightly',
  backup_plan_id: 2,
  backup_plan_run_id: null,
  backup_plan_name: 'nightly',
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
}

const meta = {
  title: 'BackgroundWork/ForegroundLaneRow',
} satisfies Meta<typeof ForegroundLaneRow>

export default meta

type Story = StoryObj<typeof meta>

export const Running: Story = {
  render: () => (
    <MemoryRouter>
      <Box sx={{ p: 3, maxWidth: 480 }}>
        <ForegroundLaneRow operation={op} />
      </Box>
    </MemoryRouter>
  ),
}
