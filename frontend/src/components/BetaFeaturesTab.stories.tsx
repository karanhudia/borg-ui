import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import BetaFeaturesTab from './BetaFeaturesTab'
import type { SystemSettings } from '../services/api'

const initialSettings: SystemSettings = {
  bypass_lock_on_info: false,
  bypass_lock_on_list: true,
  lock_breaking_enabled: true,
  borg2_fast_browse_beta_enabled: true,
  mqtt_beta_enabled: false,
}

function createMockQueryClient() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  })
  queryClient.setQueryData(['systemSettings'], { settings: initialSettings })
  return queryClient
}

const meta = {
  title: 'Components/BetaFeaturesTab',
  component: BetaFeaturesTab,
  parameters: {
    layout: 'fullscreen',
  },
  decorators: [
    (Story) => (
      <QueryClientProvider client={createMockQueryClient()}>
        <Story />
      </QueryClientProvider>
    ),
  ],
} satisfies Meta<typeof BetaFeaturesTab>

export default meta

type Story = StoryObj<typeof meta>

export const CurrentBetaSwitches: Story = {
  render: () => (
    <Box sx={{ maxWidth: 960, mx: 'auto', p: 3 }}>
      <BetaFeaturesTab />
    </Box>
  ),
}
