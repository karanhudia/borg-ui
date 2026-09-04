import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Stack } from '@mui/material'
import PipelineStageColumn from './PipelineStageColumn'
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
  title: 'BackgroundWork/PipelineStageColumn',
} satisfies Meta<typeof PipelineStageColumn>

export default meta

type Story = StoryObj<typeof meta>

export const Mixed: Story = {
  render: () => (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" spacing={3}>
        <PipelineStageColumn
          stage={{
            key: 'connect',
            label: 'Connect',
            operations: [
              op({ id: 1, kind: 'import_connect', status: 'queued', repository: 'offsite' }),
            ],
          }}
        />
        <PipelineStageColumn
          stage={{
            key: 'stats',
            label: 'Stats',
            operations: [op({ id: 2, kind: 'stats', repository: 'nas' })],
          }}
        />
        <PipelineStageColumn
          stage={{
            key: 'history_index',
            label: 'History index',
            operations: [
              op({
                id: 3,
                kind: 'history_index',
                repository: 'photos',
                progress_current: 14,
                progress_total: 38,
                progress_percent: 37,
              }),
            ],
          }}
          workerControl={
            <Box sx={{ fontSize: 12, color: 'text.secondary', mt: 1 }}>workers: index 2</Box>
          }
        />
        <PipelineStageColumn
          stage={{
            key: 'ready',
            label: 'Ready',
            operations: [op({ id: 4, kind: 'stats', status: 'completed', repository: 'laptop' })],
          }}
        />
      </Stack>
    </Box>
  ),
}

export const WithFailure: Story = {
  render: () => (
    <Box sx={{ p: 3, maxWidth: 260 }}>
      <PipelineStageColumn
        stage={{
          key: 'archives',
          label: 'Archives',
          operations: [
            op({
              id: 5,
              kind: 'archive_sync',
              status: 'failed',
              repository: 'offsite',
              progress_percent: null,
            }),
          ],
        }}
        onRetry={() => {}}
      />
    </Box>
  ),
}
