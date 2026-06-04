import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Stack, Typography } from '@mui/material'
import { Cpu } from 'lucide-react'
import { ArcGauge } from './charts'
import { ResourceGaugeGrid } from './ResourceGaugeGrid'
import { makeT, TokenContext } from './tokens'

const T = makeT(false)

const surface = {
  bgcolor: T.bgCard,
  border: `1px solid ${T.border}`,
  borderRadius: T.radius,
} as const

const meta = {
  title: 'Pages/DashboardV3/ResourceGaugeGrid',
  component: ResourceGaugeGrid,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof ResourceGaugeGrid>

export default meta

type Story = StoryObj<typeof meta>

export const NarrowRail: Story = {
  args: {
    children: null,
  },
  render: () => (
    <TokenContext.Provider value={T}>
      <Box sx={{ width: 200, maxWidth: 'calc(100vw - 32px)', ...surface, p: 2 }}>
        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: 2 }}>
          <Cpu size={14} color={T.textMuted} />
          <Typography sx={{ fontSize: '0.8125rem', fontWeight: 600, color: T.textPrimary }}>
            Resources
          </Typography>
        </Stack>
        <ResourceGaugeGrid>
          <ArcGauge value={4} color={T.blue} label="CPU" sub="2c" />
          <ArcGauge value={78} color={T.amber} label="MEM" sub="3.0/3.8G" />
          <ArcGauge value={38} color={T.blue} label="DISK" sub="54/144G" />
        </ResourceGaugeGrid>
      </Box>
    </TokenContext.Provider>
  ),
}
