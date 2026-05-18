import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import RepositoryWipeDialog from './RepositoryWipeDialog'
import type { Repository, RepositoryWipeJob } from '../types'

const repository: Repository = {
  id: 7,
  name: 'Primary Repository',
  path: '/mnt/borg/primary',
  borg_version: 2,
  archive_count: 3,
  total_size: '42.8 GB',
  last_backup: '2026-05-17T21:15:00Z',
}

const preview: RepositoryWipeJob = {
  id: 88,
  repository_id: repository.id,
  status: 'previewed',
  phase: 'preview',
  archive_count: 3,
  archive_fingerprint: 'sha256:8d4db8a7e9a5c9d3',
  run_compact: true,
  progress: 0,
  progress_message: 'Wipe preview generated',
  has_logs: false,
  blocked: false,
  blocking_reason: null,
  protected_archives: [],
  dry_run_output:
    'Would delete archive primary-2026-05-15\nWould delete archive primary-2026-05-16\nWould delete archive primary-2026-05-17',
  archives: [
    {
      identity: 'archive-id-2026-05-15',
      id: 'archive-id-2026-05-15',
      name: 'primary-2026-05-15',
      time: '2026-05-15T21:15:00Z',
    },
    {
      identity: 'archive-id-2026-05-16',
      id: 'archive-id-2026-05-16',
      name: 'primary-2026-05-16',
      time: '2026-05-16T21:15:00Z',
    },
    {
      identity: 'archive-id-2026-05-17',
      id: 'archive-id-2026-05-17',
      name: 'primary-2026-05-17',
      time: '2026-05-17T21:15:00Z',
    },
  ],
}

const meta = {
  title: 'Components/RepositoryWipeDialog',
  component: RepositoryWipeDialog,
  parameters: {
    layout: 'centered',
  },
  args: {
    open: true,
    repository,
    preview,
    job: null,
    isPreviewLoading: false,
    isExecuteLoading: false,
    onClose: () => {},
    onGeneratePreview: () => {},
    onExecute: () => {},
    onCancelPreview: () => {},
  },
  render: (args) => (
    <Box sx={{ width: 760, minHeight: 640 }}>
      <RepositoryWipeDialog {...args} />
    </Box>
  ),
} satisfies Meta<typeof RepositoryWipeDialog>

export default meta

type Story = StoryObj<typeof meta>

export const ConfirmationReady: Story = {}

export const ProtectedArchiveBlocked: Story = {
  args: {
    preview: {
      ...preview,
      blocked: true,
      blocking_reason: 'protected_archives',
      protected_archives: ['primary-2026-05-17'],
      dry_run_output: '',
    },
  },
}

export const CompactFailureRecovery: Story = {
  args: {
    job: {
      ...preview,
      status: 'completed_compaction_failed',
      phase: 'compact_failed',
      progress: 100,
      progress_message: 'Repository contents wipe completed',
      error_message: 'borg compact failed with exit code 2',
    },
  },
}
