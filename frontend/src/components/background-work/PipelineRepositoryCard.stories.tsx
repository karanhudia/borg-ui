import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import PipelineRepositoryCard from './PipelineRepositoryCard'
import type { OperationItem } from '../../types/operations'

const op = (overrides: Partial<OperationItem>): OperationItem => ({
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
  repository_id: 1,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: new Date(Date.now() - 41 * 60 * 1000).toISOString(),
  completed_at: null,
  created_at: new Date().toISOString(),
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
  ...overrides,
})

const meta = {
  component: PipelineRepositoryCard,
  title: 'BackgroundWork/PipelineRepositoryCard',
  decorators: [
    (Story) => (
      <Box sx={{ width: 240, p: 2 }}>
        <Story />
      </Box>
    ),
  ],
} satisfies Meta<typeof PipelineRepositoryCard>

export default meta
type Story = StoryObj<typeof meta>

export const Running: Story = {
  args: { operation: op({}), onOpen: () => {} },
}

export const Waiting: Story = {
  args: {
    operation: op({ status: 'queued', started_at: null, progress_percent: null }),
    onOpen: () => {},
  },
}

export const Failed: Story = {
  args: {
    operation: op({ status: 'failed', error_message: 'borg list timed out' }),
    onRetry: () => {},
    onOpen: () => {},
  },
}

export const FailedWithoutRetry: Story = {
  args: {
    operation: op({ kind: 'import_connect', category: 'import', status: 'failed' }),
    onRetry: () => {},
    onOpen: () => {},
  },
}
