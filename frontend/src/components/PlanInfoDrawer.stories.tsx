import { useRef, type ComponentProps } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, CssBaseline } from '@mui/material'
import { ThemeProvider } from '@mui/material/styles'
import { darkTheme } from '../theme'
import PlanInfoDrawer from './PlanInfoDrawer'

const featureMap = {
  borg_v2: 'pro',
  backup_plan_multi_repository: 'pro',
  extra_users: 'pro',
  rbac: 'enterprise',
} as const

function PlanInfoDrawerStory(args: ComponentProps<typeof PlanInfoDrawer>) {
  const hostRef = useRef<HTMLDivElement>(null)

  return (
    <Box
      ref={hostRef}
      sx={{
        minHeight: 520,
        width: '100%',
        bgcolor: 'background.default',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <PlanInfoDrawer
        {...args}
        open={true}
        onClose={() => {}}
        container={() => hostRef.current ?? document.body}
      />
    </Box>
  )
}

const meta = {
  title: 'Components/PlanInfoDrawer',
  component: PlanInfoDrawer,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof PlanInfoDrawer>

export default meta

type Story = StoryObj<typeof meta>

export const CommunityUpgradeDrawer: Story = {
  args: {
    open: true,
    plan: 'community',
    appVersion: '2.0.2',
    features: featureMap,
    onClose: () => {},
  },
  render: (args) => <PlanInfoDrawerStory {...args} />,
}

export const DarkCommunityUpgradeDrawer: Story = {
  args: {
    open: true,
    plan: 'community',
    appVersion: '2.0.2',
    features: featureMap,
    onClose: () => {},
  },
  render: (args) => (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <PlanInfoDrawerStory {...args} />
    </ThemeProvider>
  ),
}
