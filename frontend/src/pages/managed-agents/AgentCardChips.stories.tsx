import type { Meta, StoryObj } from '@storybook/react-vite'
import type { ReactNode } from 'react'
import { Box, ThemeProvider, Typography } from '@mui/material'
import { darkTheme } from '../../theme'
import AgentBorgVersionChip from './AgentBorgVersionChip'
import AgentManualUpgradeChip from './AgentManualUpgradeChip'
import AgentUpgradeChip from './AgentUpgradeChip'
import AgentUpgradeStateChip from './AgentUpgradeStateChip'

/**
 * The chip cluster in the top-right corner of an agent card, rendered with the
 * same flex row the card uses, so any chip that sits a few pixels off its
 * neighbours shows up here.
 */
function ChipRow({ children }: { children: ReactNode }) {
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        flexWrap: 'wrap',
        minWidth: 0,
        gap: 0.5,
        width: 420,
        p: 2,
        bgcolor: 'background.paper',
      }}
    >
      <Typography
        sx={{
          fontSize: '0.58rem',
          fontWeight: 500,
          color: 'text.disabled',
          letterSpacing: '0.02em',
        }}
      >
        v0.1.0
      </Typography>
      {children}
    </Box>
  )
}

const meta: Meta<typeof ChipRow> = {
  title: 'Managed Agents/AgentCardChips',
  component: ChipRow,
}
export default meta

type Story = StoryObj<typeof ChipRow>

const unknownAndManual = (
  <>
    <AgentUpgradeChip status="unknown" />
    <AgentManualUpgradeChip />
  </>
)

const everything = (
  <>
    <AgentUpgradeChip status="outdated" targetVersion="0.1.3" />
    <AgentBorgVersionChip desiredBorgVersion="2" borgVersions={[{ major: 1 }]} />
    <AgentManualUpgradeChip />
    <AgentUpgradeStateChip state="requested" targetVersion="0.1.3" />
  </>
)

export const UnknownAndManual: Story = {
  render: () => <ChipRow>{unknownAndManual}</ChipRow>,
}

export const Everything: Story = {
  render: () => <ChipRow>{everything}</ChipRow>,
}

export const EverythingDark: Story = {
  render: () => (
    <ThemeProvider theme={darkTheme}>
      <ChipRow>{everything}</ChipRow>
    </ThemeProvider>
  ),
}
