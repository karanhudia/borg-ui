import type { Meta, StoryObj } from '@storybook/react-vite'
import RebuildMenu from './RebuildMenu'

const meta = {
  title: 'BackgroundWork/RebuildMenu',
} satisfies Meta<typeof RebuildMenu>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => <RebuildMenu onSelect={() => {}} />,
}
