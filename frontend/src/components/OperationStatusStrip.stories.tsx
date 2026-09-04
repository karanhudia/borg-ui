import type { Meta, StoryObj } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Box } from '@mui/material'
import OperationStatusStrip from './OperationStatusStrip'

const meta = {
  title: 'Components/OperationStatusStrip',
} satisfies Meta<typeof OperationStatusStrip>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => (
    <QueryClientProvider client={new QueryClient()}>
      <Box sx={{ p: 3, maxWidth: 480 }}>
        <OperationStatusStrip repositoryId={1} />
      </Box>
    </QueryClientProvider>
  ),
}
