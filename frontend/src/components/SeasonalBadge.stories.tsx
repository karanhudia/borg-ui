import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'
import { Box, Typography } from '@mui/material'
import SeasonalBadge from './SeasonalBadge'
import manifest from '../data/announcements.json'
import type { Announcement } from '../types/announcements'

const blackFriday = manifest.announcements.find(
  (entry) => entry.type === 'seasonal_badge'
) as Announcement

// Stand-in for the sidebar header: same 16px inset and 38px logo tile.
function SidebarHeader({ children }: { children: React.ReactNode }) {
  return (
    <Box
      sx={{
        position: 'relative',
        width: 260,
        height: 64,
        pl: 2,
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        bgcolor: 'background.paper',
        borderBottom: 1,
        borderColor: 'divider',
      }}
    >
      <Box
        sx={{
          width: 38,
          height: 38,
          borderRadius: 2,
          background: 'linear-gradient(135deg, #065f46 0%, #059669 100%)',
          boxShadow: '0 4px 14px rgba(5,150,105,0.4)',
        }}
      />
      <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: '0.14em' }}>
        Borg UI
      </Typography>
      {children}
    </Box>
  )
}

const meta = {
  title: 'Components/SeasonalBadge',
  component: SeasonalBadge,
  args: { badge: blackFriday, showSale: true, onSaleClick: fn() },
  beforeEach: () => {
    try {
      sessionStorage.clear()
    } catch {
      // Storage blocked in this preview; the burst just plays.
    }
  },
  render: (args) => (
    <SidebarHeader>
      <SeasonalBadge {...args} />
    </SidebarHeader>
  ),
} satisfies Meta<typeof SeasonalBadge>

export default meta
type Story = StoryObj<typeof meta>

/** Community install during the sale: the emoji links to /buy. */
export const CommunitySale: Story = {}

/** Pro and Lite: same festive mark, no sale line, not a link. */
export const PaidPlan: Story = { args: { showSale: false } }

/** A festival with no sale and no animation, e.g. Diwali. */
export const NoSaleNoEffect: Story = {
  args: {
    showSale: false,
    badge: {
      id: 'badge-diwali-story',
      type: 'seasonal_badge',
      emoji: '🪔',
      effect: 'none',
      title: 'Happy Diwali',
      message: 'Wishing you a bright festival of lights.',
    },
  },
}
