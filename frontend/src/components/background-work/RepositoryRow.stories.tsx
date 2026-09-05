import type { Meta, StoryObj } from '@storybook/react-vite'
import { MemoryRouter } from 'react-router-dom'
import { Box } from '@mui/material'
import RepositoryRow from './RepositoryRow'
import type { RepositoryTrack, StageState } from './repositoryTrack'
import type { OperationItem } from '../../types/operations'

const op = (overrides: Partial<OperationItem>): OperationItem =>
  ({
    activity_key: null,
    id: 1,
    type: 'operation',
    kind: 'stats',
    category: 'index',
    status: 'queued',
    trigger: 'reconcile',
    priority: 20,
    run_id: 'r1',
    depends_on_id: null,
    repository_id: 3,
    repository: 'nas',
    repository_path: '/mnt/nas',
    started_at: null,
    completed_at: null,
    created_at: null,
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
  }) as OperationItem

const stage = (key: StageState['key'], overrides: Partial<StageState> = {}): StageState => ({
  key,
  status: 'idle',
  operation: null,
  reason: null,
  ...overrides,
})

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60 * 1000).toISOString()

const meta = {
  title: 'BackgroundWork/RepositoryRow',
  component: RepositoryRow,
  parameters: { layout: 'padded' },
  args: { onOpen: () => {}, onRetry: () => {}, onRebuild: () => {} },
  decorators: [
    (Story) => (
      <MemoryRouter>
        <Box sx={{ maxWidth: 1100, px: 2.5, border: 1, borderColor: 'divider', borderRadius: 2 }}>
          <Story />
        </Box>
      </MemoryRouter>
    ),
  ],
} satisfies Meta<typeof RepositoryRow>

export default meta

type Story = StoryObj<typeof meta>

const base: RepositoryTrack = {
  repositoryId: 3,
  repositoryName: 'nas-backup',
  foreground: null,
  stages: [stage('connect'), stage('stats'), stage('archives'), stage('history')],
}

export const Indexing: Story = {
  args: {
    track: {
      ...base,
      stages: [
        stage('connect', { status: 'done', operation: op({ status: 'completed' }) }),
        stage('stats', { status: 'done', operation: op({ status: 'completed' }) }),
        stage('archives', {
          status: 'running',
          operation: op({
            status: 'running',
            started_at: minutesAgo(3),
            progress_percent: 40,
            progress_current: 14,
            progress_total: 38,
          }),
        }),
        stage('history', { status: 'waiting', operation: op({}), reason: 'workers' }),
      ],
    },
  },
}

export const BackupHoldsTheRepository: Story = {
  args: {
    track: {
      ...base,
      foreground: op({
        id: 7,
        kind: 'backup',
        category: 'backup',
        status: 'running',
        started_at: minutesAgo(41),
        backup_plan_name: 'nightly',
      }),
      stages: [
        stage('connect'),
        stage('stats', { status: 'waiting', operation: op({}), reason: 'lane_busy' }),
        stage('archives', { status: 'waiting', operation: op({}), reason: 'lane_busy' }),
        stage('history', { status: 'waiting', operation: op({}), reason: 'lane_busy' }),
      ],
    },
  },
}

export const FailedStage: Story = {
  args: {
    track: {
      ...base,
      stages: [
        stage('connect', { status: 'done', operation: op({ status: 'completed' }) }),
        stage('stats', { status: 'done', operation: op({ status: 'completed' }) }),
        stage('archives', { status: 'failed', operation: op({ status: 'failed' }) }),
        stage('history'),
      ],
    },
  },
}

export const Paused: Story = {
  args: {
    track: {
      ...base,
      stages: [
        stage('connect', { status: 'done', operation: op({ status: 'completed' }) }),
        stage('stats', { status: 'waiting', operation: op({}), reason: 'paused' }),
        stage('archives'),
        stage('history'),
      ],
    },
  },
}
