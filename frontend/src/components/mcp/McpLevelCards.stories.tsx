import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import McpLevelCards from './McpLevelCards'
import type { McpLevel } from '../../services/api'

function Harness(props: { available: McpLevel[]; cap: McpLevel }) {
  const [value, setValue] = useState<McpLevel>('read')
  return (
    <Box sx={{ maxWidth: 560 }}>
      <McpLevelCards value={value} onChange={setValue} {...props} />
    </Box>
  )
}

const meta: Meta<typeof Harness> = {
  title: 'MCP/McpLevelCards',
  component: Harness,
}
export default meta
type Story = StoryObj<typeof Harness>

export const ReadOnlyAvailable: Story = { args: { available: ['read'], cap: 'full' } }
export const CappedAtOperate: Story = {
  args: { available: ['read', 'operate', 'manage', 'full'], cap: 'operate' },
}
export const AllAvailable: Story = {
  args: { available: ['read', 'operate', 'manage', 'full'], cap: 'full' },
}
