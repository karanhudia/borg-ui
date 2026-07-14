import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Typography } from '@mui/material'
import { Hourglass } from 'lucide-react'
import StorageBrowserDialog, { type StorageBrowserItem } from './StorageBrowserDialog'

const meta = {
  title: 'Components/StorageBrowserDialog',
  component: StorageBrowserDialog,
  parameters: { layout: 'fullscreen' },
  args: {
    open: true,
    title: 'Archive Contents',
    subtitle: 'backup-2026-07-08',
    currentPath: '',
    rootLabel: 'Root',
    closeLabel: 'Close',
    emptyDirectoryLabel: 'This directory is empty',
    onClose: () => {},
    onNavigate: () => {},
  },
} satisfies Meta<typeof StorageBrowserDialog>

export default meta
type Story = StoryObj<typeof meta>

const items: StorageBrowserItem[] = [
  { name: 'home', path: 'home', type: 'directory', size: null },
  { name: 'etc', path: 'etc', type: 'directory', size: null },
  {
    name: 'notes.txt',
    path: 'notes.txt',
    type: 'file',
    size: 1024,
    modified: '2026-07-08T10:00:00Z',
  },
]

const slowLoadingHint = (
  <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, px: 1.5, py: 1 }}>
    <Hourglass size={17} style={{ marginTop: 2, flexShrink: 0 }} />
    <Typography variant="body2" color="text.secondary">
      This archive is large, so listing its files takes a little longer. Hang tight.
    </Typography>
  </Box>
)

export const Populated: Story = {
  args: { items, showModifiedColumn: true },
}

export const Loading: Story = {
  args: { items: null, isLoading: true },
}

// The loadingHint slot: a friendly note rendered above the skeletons while a slow
// (managed-agent) listing is still running.
export const LoadingWithHint: Story = {
  args: { items: null, isLoading: true, loadingHint: slowLoadingHint },
}
