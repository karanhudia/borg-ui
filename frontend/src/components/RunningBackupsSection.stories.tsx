import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import RunningBackupsSection from './RunningBackupsSection'
import type { BackupJob } from '../types'

// A server backup whose source total is known: the percentage and the ETA show.
const withKnownTotal: BackupJob = {
  id: 812,
  repository: '/backups/accounting',
  status: 'running',
  started_at: '2026-05-23T02:01:00Z',
  execution_mode: 'local',
  progress: 64,
  progress_details: {
    original_size: 148_707_246_080,
    compressed_size: 101_000_000_000,
    deduplicated_size: 2_400_000_000,
    nfiles: 12_004,
    current_file: '/srv/accounting/ledgers/2026/invoices-2026-05.sqlite',
    backup_speed: 182.4,
    total_expected_size: 232_000_000_000,
    estimated_time_remaining: 455,
  },
}

// An agent backup: borg create reports no total, so there is no percentage
// (null). The job reads data, so its stage is "processing", and the bar is
// hidden while the figures Borg reports keep moving.
const agentWithoutPercentage: BackupJob = {
  ...withKnownTotal,
  id: 813,
  repository: '/backups/workstation',
  execution_mode: 'agent',
  progress: null,
  progress_details: {
    original_size: 846_634_729_941,
    compressed_size: 512_000_000_000,
    deduplicated_size: 9_800_000_000,
    nfiles: 584_280,
    current_file: '/home/k/projects/report.pdf',
    backup_speed: 96.1,
    total_expected_size: 0,
    estimated_time_remaining: 0,
  },
}

// Nothing read yet and no percentage: the stage is "initializing".
const initializing: BackupJob = {
  ...agentWithoutPercentage,
  id: 814,
  progress_details: {
    original_size: 0,
    nfiles: 0,
    current_file: '',
    total_expected_size: 0,
    estimated_time_remaining: 0,
  },
}

const meta = {
  title: 'Components/RunningBackupsSection',
  component: RunningBackupsSection,
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    runningBackupJobs: [withKnownTotal],
    onCancelBackup: () => {},
    isCancelling: false,
    onViewLogs: () => {},
  },
  render: (args) => (
    <Box sx={{ p: 3, maxWidth: 960 }}>
      <RunningBackupsSection {...args} />
    </Box>
  ),
} satisfies Meta<typeof RunningBackupsSection>

export default meta

type Story = StoryObj<typeof meta>

export const KnownTotal: Story = {}

export const AgentBackupWithoutPercentage: Story = {
  args: {
    runningBackupJobs: [agentWithoutPercentage],
  },
}

export const Initializing: Story = {
  args: {
    runningBackupJobs: [initializing],
  },
}
