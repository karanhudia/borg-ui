import type { Meta, StoryObj } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Box } from '@mui/material'
import BackgroundWorkTab from './BackgroundWorkTab'

const meta = {
  title: 'Settings/BackgroundWorkTab',
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof BackgroundWorkTab>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => (
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <Box sx={{ p: 3 }}>
          <BackgroundWorkTab />
        </Box>
      </MemoryRouter>
    </QueryClientProvider>
  ),
}
