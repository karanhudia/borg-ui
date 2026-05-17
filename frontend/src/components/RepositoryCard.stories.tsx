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

const noop = () => {}
const canDo = (_action: RepoAction) => true
const defaultArgs = {
  repository: sampleRepository,
  isInJobsSet: false,
  onViewInfo: noop,
  onCheck: noop,
  onCompact: noop,
  onPrune: noop,
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
