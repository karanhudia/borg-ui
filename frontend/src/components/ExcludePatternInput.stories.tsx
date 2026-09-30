import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'

import ExcludePatternInput from './ExcludePatternInput'

function Harness({ initial }: { initial: string[] }) {
  const [patterns, setPatterns] = useState(initial)
  return (
    <Box sx={{ width: { xs: '100%', sm: 560 }, p: 2 }}>
      <ExcludePatternInput patterns={patterns} onChange={setPatterns} onBrowseClick={() => {}} />
    </Box>
  )
}

const meta = {
  title: 'Components/ExcludePatternInput',
  component: Harness,
  parameters: { layout: 'centered' },
} satisfies Meta<typeof Harness>

export default meta
type Story = StoryObj<typeof meta>

export const Short: Story = { args: { initial: ['*.log', 'node_modules'] } }

// Docker volume paths have no spaces; they must wrap inside the row.
export const LongPaths: Story = {
  args: {
    initial: [
      '/local/home/docker-data/docker/volumes/f4eacb753d4773abd449c209d03a1d909e9dec4e880a463701c0c7527403b006/_data/thumbs',
      '/local/home/docker-data/docker/volumes/f4eacb753d4773abd449c209d03a1d909e9dec4e880a463701c0c7527403b006/_data/encoded-video',
    ],
  },
}
