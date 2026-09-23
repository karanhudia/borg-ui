import { Box } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { SpaceSavingsPanel } from './SpaceSavingsPanel'
import { makeT, TokenContext } from './tokens'
import type { SpaceSaving } from './types'

// Follows the Storybook theme toolbar, so each story renders both modes.
const useStoryT = () => makeT(useTheme().palette.mode === 'dark')

const retention = (keep_daily: number) => ({
  keep_hourly: 0,
  keep_daily,
  keep_weekly: 4,
  keep_monthly: 6,
  keep_quarterly: 0,
  keep_yearly: 1,
  keep_within: null,
})

const rows: SpaceSaving[] = [
  {
    repository_id: 3,
    repository_name: 'nas',
    candidate: 'standard',
    label: 'Standard',
    retention: retention(7),
    freed_at_least: 40 * 1024 ** 3,
    computed_at: '2026-09-18T01:00:00Z',
    stale: false,
  },
  {
    repository_id: 4,
    repository_name: 'offsite',
    candidate: 'wide',
    label: 'Wide',
    retention: retention(30),
    freed_at_least: 120 * 1024 ** 3,
    computed_at: '2026-09-18T01:00:00Z',
    stale: false,
  },
]

const meta = {
  title: 'Pages/DashboardV3/SpaceSavingsPanel',
  component: SpaceSavingsPanel,
  parameters: {
    layout: 'padded',
  },
} satisfies Meta<typeof SpaceSavingsPanel>

export default meta
type Story = StoryObj<typeof meta>

export const ThreeRows: Story = {
  args: { rows, onNavigate: () => {} },
  render: function Render(args) {
    const T = useStoryT()
    return (
      <TokenContext.Provider value={T}>
        <Box sx={{ width: 340, maxWidth: '100%', color: T.textPrimary }}>
          <SpaceSavingsPanel {...args} />
        </Box>
      </TokenContext.Provider>
    )
  },
}

export const OneStale: Story = {
  args: { rows: [{ ...rows[0], stale: true }], onNavigate: () => {} },
  render: function Render(args) {
    const T = useStoryT()
    return (
      <TokenContext.Provider value={T}>
        <Box sx={{ width: 340, maxWidth: '100%', color: T.textPrimary }}>
          <SpaceSavingsPanel {...args} />
        </Box>
      </TokenContext.Provider>
    )
  },
}
