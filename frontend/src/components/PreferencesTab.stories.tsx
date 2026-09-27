import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PreferencesTab from './PreferencesTab'
import { authAPI, settingsAPI } from '../services/api'

// The analytics section is the toggle and its description only; it no longer
// links to the retired public Umami dashboard.
const preferences = (analyticsEnabled: boolean) => ({
  success: true,
  preferences: {
    analytics_enabled: analyticsEnabled,
    analytics_consent_given: true,
    analytics_instance_key: 'a'.repeat(64),
    analytics_user_key: 'b'.repeat(64),
  },
})

function createMockQueryClient(analyticsEnabled: boolean) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  })
  queryClient.setQueryData(['preferences'], preferences(analyticsEnabled))
  return queryClient
}

const meta = {
  title: 'Components/PreferencesTab',
  component: PreferencesTab,
  parameters: {
    layout: 'fullscreen',
  },
  // Flipping the switch saves, refetches the preferences and reloads the analytics
  // preference. Stub those calls for these stories so they never reach a backend (the
  // refetch returns what was saved), and restore them after.
  beforeEach: () => {
    const { getPreferences, updatePreferences } = settingsAPI
    const { getAuthConfig } = authAPI
    let saved = true
    settingsAPI.getPreferences = async () =>
      ({ data: preferences(saved) }) as Awaited<ReturnType<typeof settingsAPI.getPreferences>>
    settingsAPI.updatePreferences = async (update) => {
      saved = Boolean(update.analytics_enabled)
      return { data: { success: true } } as Awaited<
        ReturnType<typeof settingsAPI.updatePreferences>
      >
    }
    authAPI.getAuthConfig = async () =>
      ({ data: { proxy_auth_enabled: false, insecure_no_auth_enabled: false } }) as Awaited<
        ReturnType<typeof authAPI.getAuthConfig>
      >
    return () => {
      settingsAPI.getPreferences = getPreferences
      settingsAPI.updatePreferences = updatePreferences
      authAPI.getAuthConfig = getAuthConfig
    }
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
