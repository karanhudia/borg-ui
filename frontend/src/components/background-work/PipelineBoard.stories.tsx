import type { Meta, StoryObj } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Box } from '@mui/material'
import PipelineBoard from './PipelineBoard'

// No API mocking layer (e.g. MSW) exists elsewhere in this codebase's
// stories, so this story shows the board's loading/empty-state branch
// only, without a mocked operationsAPI response.
const meta = {
  title: 'BackgroundWork/PipelineBoard',
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof PipelineBoard>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => (
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <Box sx={{ p: 3 }}>
          <PipelineBoard canManage />
        </Box>
      </MemoryRouter>
    </QueryClientProvider>
  ),
}
