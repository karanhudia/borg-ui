import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import BetaFeaturesTab from './BetaFeaturesTab'
import { settingsAPI } from '../services/api'
import type { SystemSettings } from '../services/api'

let currentSettings: SystemSettings = {
  bypass_lock_on_info: false,
  bypass_lock_on_list: true,
  borg2_fast_browse_beta_enabled: true,
  mqtt_beta_enabled: false,
}

settingsAPI.getSystemSettings = async () =>
  ({
    data: { settings: currentSettings },
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {},
  }) as Awaited<ReturnType<typeof settingsAPI.getSystemSettings>>

settingsAPI.updateSystemSettings = async (settings: SystemSettings) => {
  currentSettings = { ...currentSettings, ...settings }
  return {
    data: { settings: currentSettings },
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {},
  } as Awaited<ReturnType<typeof settingsAPI.updateSystemSettings>>
}

const meta = {
  title: 'Components/BetaFeaturesTab',
  component: BetaFeaturesTab,
  parameters: {
    layout: 'fullscreen',
  },
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
