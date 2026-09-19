import type { Meta, StoryObj } from '@storybook/react-vite'
import PrunePreviewNumbers from './PrunePreviewNumbers'

const meta = {
  title: 'Components/Prune/PrunePreviewNumbers',
  component: PrunePreviewNumbers,
} satisfies Meta<typeof PrunePreviewNumbers>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    deletedCount: 4,
    keptCount: 12,
    freedAtLeast: 41_200_000_000,
    footprintBefore: 900_000_000_000,
    footprintAfterAtMost: 858_800_000_000,
  },
}

export const NotMeasured: Story = {
  args: {
    deletedCount: 4,
    keptCount: 12,
    freedAtLeast: 0,
    footprintBefore: null,
    footprintAfterAtMost: null,
  },
}

export const FreedKnown: Story = {
  args: {
    deletedCount: 5,
    keptCount: 13,
    freedAtLeast: 1_400_000,
    lostSize: 3_440_000,
    footprintBefore: 22_900_000_000,
    footprintAfterAtMost: 22_898_600_000,
  },
}
