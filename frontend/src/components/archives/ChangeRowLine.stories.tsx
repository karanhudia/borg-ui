import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import ChangeRowLine from './ChangeRowLine'
import type { ChangeRow } from '../../types/archives'

const row = (overrides: Partial<ChangeRow>): ChangeRow => ({
  path: 'home/example/docs/report.xlsx',
  change: 'modified',
  size_before: 374_000,
  size_after: 412_000,
  mode_changed: false,
  owner_changed: false,
  summary_count: null,
  ...overrides,
})

const meta: Meta<typeof ChangeRowLine> = {
  title: 'Components/Archives/ChangeRowLine',
  component: ChangeRowLine,
  decorators: [
    (Story) => (
      <Box sx={{ maxWidth: 900, border: 1, borderColor: 'divider', borderRadius: 2, py: 0.5 }}>
        <Story />
      </Box>
    ),
  ],
}

export default meta

type Story = StoryObj<typeof ChangeRowLine>

export const Modified: Story = { args: { row: row({}) } }
export const Added: Story = {
  args: {
    row: row({
      path: 'home/example/photos/sample.jpg',
      change: 'added',
      size_before: null,
      size_after: 4_200_000,
    }),
  },
}
export const Removed: Story = {
  args: {
    row: row({
      path: 'home/example/archive/old-file.pdf',
      change: 'removed',
      size_before: 890_000,
      size_after: null,
    }),
  },
}
export const Summary: Story = {
  args: {
    row: row({
      path: 'home/example/projects',
      change: 'summary',
      size_before: null,
      size_after: null,
      summary_count: 14,
    }),
  },
}
