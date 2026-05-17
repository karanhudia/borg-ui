import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import CheckWarningDialog from './CheckWarningDialog'

const noop = () => {}

const meta = {
  title: 'Components/CheckWarningDialog',
  component: CheckWarningDialog,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof CheckWarningDialog>

export default meta

type Story = StoryObj<typeof meta>

export const AdvancedFlags: Story = {
  args: {
    open: true,
    repositoryName: 'Production Archive',
    borgVersion: 2,
    initialMaxDuration: 0,
    initialCheckExtraFlags: '--repair --verify-data',
    isLoading: false,
    onConfirm: noop,
    onCancel: noop,
  },
  render: (args) => (
    <Box sx={{ minHeight: 520 }}>
      <CheckWarningDialog {...args} />
    </Box>
  ),
}
