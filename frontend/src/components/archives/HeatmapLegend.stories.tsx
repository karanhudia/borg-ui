import type { Meta, StoryObj } from '@storybook/react-vite'
import HeatmapLegend from './HeatmapLegend'

const meta = {
  title: 'Components/Archives/HeatmapLegend',
  component: HeatmapLegend,
} satisfies Meta<typeof HeatmapLegend>

export default meta

type Story = StoryObj<typeof meta>

export const Community: Story = {
  args: {
    flagsAvailable: { missed_run: true, size_outlier: false, duration_outlier: false },
  },
}

export const Pro: Story = {
  args: {
    flagsAvailable: { missed_run: true, size_outlier: true, duration_outlier: true },
  },
}

// A calendar whose days carry no flags at all (the prune preview): the rows
// are left out rather than offered as an upgrade.
export const NoFlags: Story = { args: { flagsAvailable: undefined } }
