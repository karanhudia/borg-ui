import { useEffect, useState, type ReactNode } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import MockAdapter from 'axios-mock-adapter'
import { Box } from '@mui/material'
import api from '../../services/api'
import McpActivityPanel from './McpActivityPanel'
import { activityRows } from './storyFixtures'

function WithActivity({
  rows,
  children,
}: {
  rows: ReturnType<typeof activityRows>
  children: ReactNode
}) {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const mock = new MockAdapter(api)
    mock.onGet(/\/settings\/mcp\/connections\/\d+\/activity/).reply((config) => {
      const before = config.params?.before_id as number | undefined
      const page = rows.filter((r) => before === undefined || r.id < before).slice(0, 50)
      return [200, page]
    })
    setReady(true)
    return () => mock.restore()
  }, [rows])
  return ready ? <Box sx={{ maxWidth: 900 }}>{children}</Box> : null
}

const meta: Meta<{ rows: ReturnType<typeof activityRows> }> = {
  title: 'MCP/McpActivityPanel',
  render: ({ rows }) => (
    <WithActivity rows={rows}>
      <McpActivityPanel connectionId={1} />
    </WithActivity>
  ),
}
export default meta
type Story = StoryObj<typeof meta>

export const EveryOutcome: Story = { args: { rows: activityRows(6) } }
export const MoreToLoad: Story = { args: { rows: activityRows(60) } }
export const Empty: Story = { args: { rows: [] } }
