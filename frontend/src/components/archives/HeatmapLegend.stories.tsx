import type { Meta, StoryObj } from '@storybook/react-vite'
import HeatmapLegend from './HeatmapLegend'

const meta = {
  title: 'Components/Archives/HeatmapLegend',
  component: HeatmapLegend,
} satisfies Meta<typeof HeatmapLegend>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = { args: { missedTotal: 2 } }

export const CadenceUnknown: Story = { args: { cadenceKnown: false } }

// A calendar whose days carry no flags at all (the prune preview): the rows
// are left out rather than named for markers it never draws.
export const NoFlags: Story = { args: { showFlags: false } }
