import type { TFunction } from 'i18next'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { fn } from 'storybook/test'
import i18n from '../../../i18n'
import { SSHPageHeader } from './SSHPageHeader'

const t = i18n.t.bind(i18n) as TFunction

const meta = {
  title: 'Remote Machines/SSHPageHeader',
  component: SSHPageHeader,
  parameters: { layout: 'fullscreen' },
  args: { t, onDeploy: fn(), onAddManual: fn() },
  render: (args) => (
    <Box sx={{ p: 3, bgcolor: 'background.default' }}>
      <SSHPageHeader {...args} />
    </Box>
  ),
} satisfies Meta<typeof SSHPageHeader>

export default meta

type Story = StoryObj<typeof meta>

/** Adding machines is page-level: the deploy dialog picks the key. */
export const WithActions: Story = { args: { showActions: true } }

/** Before a system key exists there is nothing to deploy. */
export const NoKeyYet: Story = { args: { showActions: false } }
