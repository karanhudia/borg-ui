import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import HubToolbar from './HubToolbar'
import { DEFAULT_TOOLBAR, type HubToolbarState } from './hubRows'

function Controlled(props: { initial?: Partial<HubToolbarState>; shown: number; total: number }) {
  const [state, setState] = useState<HubToolbarState>({ ...DEFAULT_TOOLBAR, ...props.initial })
  return <HubToolbar state={state} onChange={setState} shown={props.shown} total={props.total} />
}

const meta = {
  title: 'BackgroundWork/HubToolbar',
  component: Controlled,
  parameters: { layout: 'fullscreen' },
  decorators: [
    (Story) => (
      <Box sx={{ p: 3 }}>
        <Story />
      </Box>
    ),
  ],
  args: { shown: 12, total: 12 },
} satisfies Meta<typeof Controlled>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const Windowed: Story = {
  args: { shown: 50, total: 340 },
}

export const AttentionView: Story = {
  args: { initial: { attention: 'attention', sort: 'synced' }, shown: 9, total: 9 },
}
