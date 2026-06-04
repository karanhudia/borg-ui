import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { SshHostField } from './SshHostField'

const meta = {
  title: 'Remote Machines/SshHostField',
  component: SshHostField,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof SshHostField>

export default meta

type Story = StoryObj<typeof meta>

export const InvalidHost: Story = {
  args: {
    label: 'Host',
    value: 'ssh://user@host',
    placeholder: '192.168.1.100 or example.com',
    hostError:
      'Enter a bare DNS name or IP address without a scheme, path, user, spaces, brackets, or port.',
    onHostChange: () => {},
  },
  render: (args) => (
    <Box sx={{ width: 420, maxWidth: 'calc(100vw - 32px)' }}>
      <SshHostField {...args} />
    </Box>
  ),
}
