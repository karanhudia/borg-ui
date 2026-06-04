import type { Meta, StoryObj } from '@storybook/react-vite'
import type { ReactNode } from 'react'
import { Box, Button } from '@mui/material'
import { Cloud, Key, ListChecks } from 'lucide-react'
import EmptyStateCard from './EmptyStateCard'

const meta = {
  title: 'Components/EmptyStateCard',
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta

export default meta

type Story = StoryObj<typeof meta>

const renderInPage = (node: ReactNode) => (
  <Box sx={{ p: 3, bgcolor: 'background.default', minHeight: '100vh' }}>{node}</Box>
)

export const Default: Story = {
  render: () =>
    renderInPage(
      <EmptyStateCard
        icon={<ListChecks size={48} />}
        title="No backup plans yet"
        description="Create your first backup plan to start protecting your data."
      />
    ),
}

export const CloudStorageNoRemotes: Story = {
  render: () =>
    renderInPage(
      <EmptyStateCard
        centered={false}
        icon={<Cloud size={48} />}
        title="No cloud storage remotes yet"
        description="Add a managed rclone remote before selecting Cloud Storage in the repository wizard."
      />
    ),
}

export const CloudStorageNoMatchWithSearch: Story = {
  render: () =>
    renderInPage(
      <EmptyStateCard
        centered={false}
        icon={<Cloud size={48} />}
        title="No matching remotes"
        description={'No remotes match "production".'}
        actions={<Button variant="outlined">Clear search</Button>}
      />
    ),
}

export const CloudStorageNoMatchFallback: Story = {
  render: () =>
    renderInPage(
      <EmptyStateCard
        centered={false}
        icon={<Cloud size={48} />}
        title="No matching remotes"
        description="No remotes match the current filters."
      />
    ),
}

export const InlineApiTokens: Story = {
  render: () =>
    renderInPage(
      <Box
        sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden' }}
      >
        <Box
          sx={{
            px: 2.5,
            py: 2,
            borderBottom: '1px solid',
            borderColor: 'divider',
            bgcolor: 'action.hover',
          }}
        >
          API Tokens
        </Box>
        <EmptyStateCard inline icon={<Key size={32} />} title="No tokens yet" />
      </Box>
    ),
}
