import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import RepositoryInfoDialog from './RepositoryInfoDialog'
import { proSystemInfo } from '../services/remoteBackends/planStoryFixtures'
import type { Repository } from '../types'
import { borg1Storage, borg2Storage, unknownStorage } from './repositoryStatsFixtures'

const brokenRepository: Repository = {
  id: 42,
  name: 'Broken Archive',
  path: '/mnt/borg/broken',
  borg_version: 1,
  encryption: 'repokey',
  compression: 'lz4',
  mode: 'full',
}

const borg1Repository: Repository = {
  id: 43,
  name: 'Production Archive',
  path: '/mnt/borg/production',
  borg_version: 1,
  encryption: 'repokey-blake2',
  compression: 'zstd,6',
  mode: 'full',
  archive_count: 21,
}

const borg2Repository: Repository = {
  ...borg1Repository,
  id: 44,
  name: 'Borg 2 on a store URL',
  path: 'rest://backup-host/repos/production',
  borg_version: 2,
  encryption: 'repokey-aes-ocb',
  archive_count: 35,
}

const meta = {
  title: 'Components/RepositoryInfoDialog',
  component: RepositoryInfoDialog,
  parameters: {
    layout: 'centered',
    // the Borg 2 body sits behind the borg_v2 plan gate
    systemInfo: proSystemInfo,
  },
  args: {
    open: true,
    repository: brokenRepository,
    onRefresh: () => {},
    onClose: () => {},
    onRunRecoveryCheck: () => {},
    canRunRecoveryCheck: true,
  },
  render: (args) => (
    <Box sx={{ width: 760, minHeight: 520 }}>
      <RepositoryInfoDialog {...args} />
    </Box>
  ),
} satisfies Meta<typeof RepositoryInfoDialog>

export default meta

type Story = StoryObj<typeof meta>

export const FailedInfoRecovery: Story = {
  args: { refreshFailed: true },
}

export const Borg1StoredStatistics: Story = {
  args: {
    repository: borg1Repository,
    storage: borg1Storage,
  },
}

export const Borg2StoredStatistics: Story = {
  args: {
    repository: borg2Repository,
    storage: borg2Storage,
  },
}

export const StatisticsUnknown: Story = {
  args: {
    repository: { ...borg2Repository, archive_count: 0 },
    storage: unknownStorage,
  },
}

export const StatisticsIndexingAfterImport: Story = {
  args: {
    repository: { ...borg2Repository, archive_count: 0 },
    storage: unknownStorage,
    indexPendingKinds: ['stats', 'archive_sync', 'history_index'],
  },
}

export const FailedInfoRecoveryUnavailable: Story = {
  args: {
    refreshFailed: true,
    canRunRecoveryCheck: false,
  },
}

export const FailedInfoWithAgentReason: Story = {
  args: {
    refreshFailed: true,
    errorMessage:
      "repository.info exited with code 2: Failed to create/acquire the lock /mnt/borg/broken/lock.exclusive ([Errno 13] Permission denied: '/mnt/borg/broken/lock.exclusive.5ic2kcji.tmp').",
  },
}
