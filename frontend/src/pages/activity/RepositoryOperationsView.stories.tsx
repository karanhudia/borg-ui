import type { Meta, StoryObj } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Box } from '@mui/material'
import RepositoryOperationsView from './RepositoryOperationsView'

// No API mocking layer exists in this codebase's stories, so this story
// shows the view's header, filters, and empty branch only.
const meta = {
  title: 'Activity/RepositoryOperationsView',
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof RepositoryOperationsView>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <Box sx={{ p: 3 }}>
          <RepositoryOperationsView repositoryId={1} />
        </Box>
      </MemoryRouter>
    </QueryClientProvider>
  ),
}
