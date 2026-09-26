import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PreferencesTab from './PreferencesTab'

// The analytics section is the toggle and its description only; it no longer
// links to the retired public Umami dashboard.
function createMockQueryClient(analyticsEnabled: boolean) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  })
  queryClient.setQueryData(['preferences'], {
    success: true,
    preferences: {
      analytics_enabled: analyticsEnabled,
      analytics_consent_given: true,
      analytics_instance_key: 'a'.repeat(64),
      analytics_user_key: 'b'.repeat(64),
    },
  })
  return queryClient
}

const meta = {
  title: 'Components/PreferencesTab',
  component: PreferencesTab,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof PreferencesTab>

export default meta

type Story = StoryObj<typeof meta>

export const AnalyticsOn: Story = {
  render: () => (
    <QueryClientProvider client={createMockQueryClient(true)}>
      <Box sx={{ maxWidth: 960, mx: 'auto', p: 3 }}>
        <PreferencesTab />
      </Box>
    </QueryClientProvider>
  ),
}

export const AnalyticsOff: Story = {
  render: () => (
    <QueryClientProvider client={createMockQueryClient(false)}>
      <Box sx={{ maxWidth: 960, mx: 'auto', p: 3 }}>
        <PreferencesTab />
      </Box>
    </QueryClientProvider>
  ),
}
