import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Typography } from '@mui/material'
import IndexModeGate from './IndexModeGate'

const meta = {
  title: 'Archives/IndexModeGate',
  component: IndexModeGate,
  parameters: { layout: 'fullscreen' },
  // The preview decorator already supplies the router every story runs in.
  decorators: [
    (Story) => (
      <Box sx={{ p: 3, maxWidth: 720 }}>
        <Story />
      </Box>
    ),
  ],
  args: {
    mode: 'full',
    children: <Typography variant="body2">The changes for this archive.</Typography>,
  },
} satisfies Meta<typeof IndexModeGate>

export default meta

type Story = StoryObj<typeof meta>

export const Indexed: Story = {}

// Spec 6.8: the panel says which mode is set and that the stored rows are
// kept, so a deliberate setting never reads as lost data.
export const ArchivesOnly: Story = {
  args: { mode: 'archives' },
}

export const NotIndexed: Story = {
  args: { mode: 'off' },
}
