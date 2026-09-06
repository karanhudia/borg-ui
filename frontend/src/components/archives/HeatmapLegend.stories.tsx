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
