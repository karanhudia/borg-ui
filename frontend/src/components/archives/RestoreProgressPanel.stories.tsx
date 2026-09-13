import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Button, IconButton, Stack, Typography } from '@mui/material'
import { CheckSquare, RotateCcw, X } from 'lucide-react'
import { RestoreProgressPanelView, type RestoreStatus } from './RestoreProgressPanel'
import { cornerPanelSx, cornerStackSx } from './cornerStack'

const meta: Meta<typeof RestoreProgressPanelView> = {
  title: 'Archives/RestoreProgressPanel',
  component: RestoreProgressPanelView,
  args: { repositoryId: 7, onDismiss: () => {} },
  parameters: { layout: 'fullscreen' },
  decorators: [
    (Story) => (
      <Box sx={cornerStackSx}>
        <Story />
      </Box>
    ),
  ],
}
export default meta
type Story = StoryObj<typeof RestoreProgressPanelView>

export const Queued: Story = { args: { job: undefined } }

export const Running: Story = {
  args: {
    job: {
      id: 42,
      status: 'running',
      destination: '/mnt/restore/2026-09-13',
      progress_details: {
        nfiles: 1284,
        current_file: 'local/Users/karanhudia/Downloads/photos/2026/summer/IMG_4123.HEIC',
        progress_percent: 37.5,
      },
    },
  },
}

export const Completed: Story = {
  args: {
    job: {
      id: 42,
      status: 'completed',
      destination: '/mnt/restore/2026-09-13',
      progress_details: { nfiles: 3209, current_file: '', progress_percent: 100 },
    },
  },
}

export const Failed: Story = {
  args: {
    job: {
      id: 42,
      status: 'failed',
      destination: '/mnt/restore/2026-09-13',
      error_message: 'Destination is not writable: /mnt/restore/2026-09-13',
    },
  },
}

export const StatusUnavailable: Story = { args: { job: undefined, statusUnavailable: true } }

/** Two restores in flight plus a fresh selection: the column stacks them,
 *  selection bar nearest the corner, so nothing covers the Restore button. */
export const StackedWithSelection: Story = {
  render: () => (
    <>
      <RestoreProgressPanelView
        repositoryId={7}
        onDismiss={() => {}}
        job={Completed.args!.job as RestoreStatus}
      />
      <RestoreProgressPanelView
        repositoryId={7}
        onDismiss={() => {}}
        job={Running.args!.job as RestoreStatus}
      />
      <Box role="toolbar" sx={cornerPanelSx}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', pl: 2, pr: 1, py: 1 }}>
          <CheckSquare size={16} />
          <Typography variant="body2" sx={{ fontWeight: 600, flex: 1 }}>
            2 selected (61.2 KB)
          </Typography>
          <IconButton size="small" sx={{ color: 'inherit' }}>
            <X size={16} />
          </IconButton>
        </Stack>
        <Box sx={{ px: 1.5, pb: 1.5, display: 'flex', justifyContent: 'flex-end' }}>
          <Button
            size="small"
            variant="contained"
            disableElevation
            startIcon={<RotateCcw size={14} />}
          >
            Restore selection
          </Button>
        </Box>
      </Box>
    </>
  ),
}
