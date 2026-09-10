import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'
import { Box } from '@mui/material'
import IndexModeSettings from './IndexModeSettings'
import type { IndexMode } from '../../types/operations'

const DEFAULT_EXCLUDES = [
  '**/.cache/**',
  '**/Library/Caches/**',
  '**/node_modules/**',
  '**/__pycache__/**',
  '**/.git/objects/**',
]

function Harness({ mode: initial }: { mode: IndexMode }) {
  const [mode, setMode] = useState<IndexMode>(initial)
  const [excludes, setExcludes] = useState<string[]>(DEFAULT_EXCLUDES)
  return (
    <Box sx={{ p: 3, maxWidth: 640 }}>
      <IndexModeSettings
        mode={mode}
        excludes={excludes}
        onModeChange={setMode}
        onExcludesChange={setExcludes}
      />
    </Box>
  )
}

const meta = {
  title: 'Repositories/IndexModeSettings',
  component: IndexModeSettings,
  parameters: { layout: 'fullscreen' },
  args: {
    mode: 'full',
    excludes: DEFAULT_EXCLUDES,
    onModeChange: () => {},
    onExcludesChange: () => {},
  },
} satisfies Meta<typeof IndexModeSettings>

export default meta

type Story = StoryObj<typeof meta>

export const Everything: Story = {
  render: () => <Harness mode="full" />,
}

// The exclude list has nothing to trim in these two, so it stays on screen
// and says why it is inactive (spec 6.7, 6.8).
export const ArchivesOnly: Story = {
  render: () => <Harness mode="archives" />,
}

export const Off: Story = {
  render: () => <Harness mode="off" />,
}
