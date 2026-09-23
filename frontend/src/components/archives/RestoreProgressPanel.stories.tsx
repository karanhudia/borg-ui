import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Button, IconButton, Typography, useTheme } from '@mui/material'
import { CheckSquare, RotateCcw, X } from 'lucide-react'
import { RestoreProgressPanelView, type RestoreStatus } from './RestoreProgressPanel'
import {
  cornerPanelFooterSx,
  cornerPanelHeaderSx,
  cornerPanelIconButtonSx,
  cornerPanelIconSx,
  cornerPanelSx,
  cornerStackSx,
} from './cornerStack'

const meta: Meta<typeof RestoreProgressPanelView> = {
  title: 'Archives/RestoreProgressPanel',
  component: RestoreProgressPanelView,
  args: { repositoryId: 7, onDismiss: () => {} },
  parameters: { layout: 'fullscreen' },
  decorators: [
    // The column is position: fixed, so the story root would have no height
    // and the snapshot runner would wait forever for it to become visible.
    (Story) => (
      <Box sx={{ minHeight: '100vh' }}>
        <Box sx={cornerStackSx}>
          <Story />
        </Box>
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
        current_file: 'local/Users/alex/Downloads/photos/2026/summer/IMG_4123.HEIC',
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

function SelectionBarMock() {
  const theme = useTheme()
  return (
    <Box role="toolbar" sx={cornerPanelSx}>
      <Box sx={cornerPanelHeaderSx}>
        <Box sx={cornerPanelIconSx(theme, 'primary')}>
          <CheckSquare size={17} />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.3 }}>
            2 selected
          </Typography>
          <Typography variant="caption" component="div" sx={{ color: 'text.secondary' }}>
            61.2 KB
          </Typography>
        </Box>
        <IconButton size="small" sx={cornerPanelIconButtonSx}>
          <X size={16} />
        </IconButton>
      </Box>
      <Box sx={cornerPanelFooterSx}>
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
  )
}

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
      <SelectionBarMock />
    </>
  ),
}
