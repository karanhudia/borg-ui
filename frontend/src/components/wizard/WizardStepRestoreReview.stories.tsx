import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import WizardStepRestoreReview, { type RestoreReviewData } from './WizardStepRestoreReview'

const reviewData: RestoreReviewData = {
  destinationType: 'local',
  destinationConnectionId: '',
  restoreStrategy: 'custom',
  customPath: '/recovery',
  restoreLayout: 'preserve_path',
  existingFiles: 'refuse',
}

const meta = {
  title: 'Components/Wizard/Restore Review',
  component: WizardStepRestoreReview,
  parameters: {
    layout: 'centered',
  },
  args: {
    data: reviewData,
    borgVersion: 2,
    selectedFiles: [
      {
        path: 'home/alex/documents',
        type: 'directory',
        mode: '',
        user: '',
        group: '',
        size: 0,
        mtime: '',
        healthy: true,
      },
    ],
    sshConnections: [],
    archiveName: 'laptop-2026-10-01',
  },
  render: (args) => (
    <Box sx={{ width: 760, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepRestoreReview {...args} />
    </Box>
  ),
} satisfies Meta<typeof WizardStepRestoreReview>

export default meta

type Story = StoryObj<typeof meta>

export const Borg2ExactRestore: Story = {}

export const Borg2RestoreIntoExistingFiles: Story = {
  args: {
    data: { ...reviewData, restoreStrategy: 'original', customPath: '', existingFiles: 'continue' },
  },
}

export const Borg1OriginalLocation: Story = {
  args: {
    borgVersion: 1,
    data: { ...reviewData, restoreStrategy: 'original', customPath: '' },
  },
}
