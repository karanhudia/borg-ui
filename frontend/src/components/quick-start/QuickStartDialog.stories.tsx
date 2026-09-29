import type { Meta, StoryObj } from '@storybook/react-vite'

import QuickStartDialog from './QuickStartDialog'

const meta = {
  title: 'Quick Start/Dialog',
  component: QuickStartDialog,
  parameters: { layout: 'fullscreen' },
  args: { open: true, onClose: () => {} },
} satisfies Meta<typeof QuickStartDialog>

export default meta
type Story = StoryObj<typeof meta>

export const FirstStep: Story = {}
