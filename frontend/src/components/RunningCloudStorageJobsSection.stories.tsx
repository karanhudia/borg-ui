import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import RunningCloudStorageJobsSection from './RunningCloudStorageJobsSection'

const meta: Meta<typeof RunningCloudStorageJobsSection> = {
  title: 'Components/RunningCloudStorageJobsSection',
  component: RunningCloudStorageJobsSection,
  decorators: [
    (Story) => (
      <Box sx={{ maxWidth: 960, p: 3, bgcolor: 'background.default' }}>
        <Story />
      </Box>
    ),
  ],
}

export default meta
type Story = StoryObj<typeof RunningCloudStorageJobsSection>

export const ActiveJobs: Story = {
  args: {
    jobs: [
      {
        id: 10,
        type: 'rclone_sync',
        status: 'pending',
        started_at: null,
        completed_at: null,
        error_message: null,
        repository: 'Cloud Mirror Repo',
        repository_path: '/repositories/cloud-mirror',
        log_file_path: null,
        triggered_by: 'initial',
        has_logs: true,
      },
      {
        id: 11,
        type: 'rclone_hydrate',
        status: 'running',
        started_at: '2026-04-01T10:00:00Z',
        completed_at: null,
        error_message: null,
        repository: 'Cloud Hydrate Repo',
        repository_path: '/repositories/cloud-hydrate',
        log_file_path: null,
        triggered_by: 'manual',
        has_logs: true,
      },
    ],
    onViewLogs: () => undefined,
  },
}
