import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import type { RepoAction } from '../hooks/usePermissions'
import { repositoriesAPI } from '../services/api'
import type { Repository } from '../types'
import RepositoryCard from './RepositoryCard'

repositoriesAPI.getRunningJobs = async (_id: number) =>
  ({
    data: {
      has_running_jobs: false,
      check_job: null,
      compact_job: null,
      prune_job: null,
      wipe_job: null,
    },
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {},
  }) as Awaited<ReturnType<typeof repositoriesAPI.getRunningJobs>>

const sampleRepository: Repository = {
  id: 42,
  name: 'Production Archive',
  path: '/mnt/borg/production',
  repository_type: 'local',
  borg_version: 2,
  encryption: 'repokey-blake2',
  compression: 'zstd,6',
  source_directories: ['/srv/app', '/etc/borg-ui', '/var/lib/postgresql'],
  mode: 'full',
  archive_count: 128,
  total_size: '842.6 GB',
  last_backup: '2026-05-15T16:30:00.000Z',
  last_check: '2026-05-14T09:15:00.000Z',
  last_compact: '2026-05-10T12:00:00.000Z',
  has_schedule: true,
  schedule_enabled: true,
  schedule_name: 'Nightly production backup',
  schedule_timezone: 'UTC',
  next_run: '2026-05-17T02:00:00.000Z',
}

const rcloneRepository: Repository = {
  ...sampleRepository,
  id: 43,
  name: 'Cloud Mirror Repository',
  path: '/mnt/borg/production',
  repository_type: 'local',
  storage_backend: 'local',
  rclone_storage: {
    repository_id: 43,
    backend: 'rclone',
    rclone_remote_id: 3,
    rclone_remote_name: 'local-test',
    rclone_remote_path: 'borg-ui/production',
    rclone_target: 'local-test:borg-ui/production',
    cache_path: '/mnt/borg/production',
    cache_present: true,
    sync_policy: 'after_success',
    sync_status: 'current',
    last_synced_at: '2026-05-15T16:35:00.000Z',
  },
}

const noop = () => {}
const canDo = (_action: RepoAction) => true
const defaultArgs = {
  repository: sampleRepository,
  isInJobsSet: false,
  onViewInfo: noop,
  onCheck: noop,
  onCompact: noop,
  onPrune: noop,
  onWipeContents: noop,
  onEdit: noop,
  onDelete: noop,
  onBackupNow: noop,
  onViewArchives: noop,
  onCreateBackupPlan: noop,
  getCompressionLabel: (compression: string) => compression.toUpperCase(),
  canManageRepository: true,
  canDo,
}

const meta = {
  title: 'Components/RepositoryCard',
  component: RepositoryCard,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof RepositoryCard>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: defaultArgs,
  render: (args) => (
    <Box sx={{ width: 620, maxWidth: 'calc(100vw - 32px)' }}>
      <RepositoryCard {...args} />
    </Box>
  ),
}

export const RcloneSynced: Story = {
  args: {
    ...defaultArgs,
    repository: rcloneRepository,
    onRcloneSync: noop,
    onRcloneHydrate: noop,
  },
  render: (args) => (
    <Box sx={{ width: 620, maxWidth: 'calc(100vw - 32px)' }}>
      <RepositoryCard {...args} />
    </Box>
  ),
}

export const EnableCloudMirror: Story = {
  args: {
    ...defaultArgs,
    repository: {
      ...sampleRepository,
      id: 46,
      name: 'Eligible Local Repository',
      storage_backend: 'local',
      execution_target: 'local',
      rclone_storage: null,
    },
  },
  render: (args) => (
    <Box sx={{ width: 620, maxWidth: 'calc(100vw - 32px)' }}>
      <RepositoryCard {...args} />
    </Box>
  ),
}

export const RcloneFailed: Story = {
  args: {
    ...defaultArgs,
    repository: {
      ...rcloneRepository,
      id: 44,
      name: 'Failed Cloud Mirror',
      rclone_storage: {
        ...rcloneRepository.rclone_storage!,
        repository_id: 44,
        sync_policy: 'manual',
        sync_status: 'failed',
        last_sync_error: 'remote local-test unavailable',
      },
    },
    onRcloneSync: noop,
    onRcloneHydrate: noop,
  },
  render: (args) => (
    <Box sx={{ width: 620, maxWidth: 'calc(100vw - 32px)' }}>
      <RepositoryCard {...args} />
    </Box>
  ),
}

export const RcloneHydrationRequired: Story = {
  args: {
    ...defaultArgs,
    repository: {
      ...rcloneRepository,
      id: 45,
      name: 'Imported Cloud Mirror',
      rclone_storage: {
        ...rcloneRepository.rclone_storage!,
        repository_id: 45,
        cache_present: false,
        sync_status: 'pending',
        last_synced_at: null,
      },
    },
    onRcloneSync: noop,
    onRcloneHydrate: noop,
  },
  render: (args) => (
    <Box sx={{ width: 620, maxWidth: 'calc(100vw - 32px)' }}>
      <RepositoryCard {...args} />
    </Box>
  ),
}
