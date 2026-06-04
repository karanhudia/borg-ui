import { useState } from 'react'
import type { TFunction } from 'i18next'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import i18n from '../../../i18n'
import { createConnectionForm } from '../formDefaults'
import type { DeployConnectionPayload } from '../types'
import { DeployKeyDialog } from './DeployKeyDialog'

const t = i18n.t.bind(i18n) as TFunction

const meta = {
  title: 'Remote Machines/DeployKeyDialog',
  component: DeployKeyDialogStory,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof DeployKeyDialogStory>

export default meta

type Story = StoryObj<typeof meta>

function DeployKeyDialogStory({
  initialForm,
}: {
  initialForm: DeployConnectionPayload
}): JSX.Element {
  const [open, setOpen] = useState(true)
  const [connectionForm, setConnectionForm] = useState(initialForm)
  const [hostError, setHostError] = useState<string>()

  return (
    <Box sx={{ p: 3, bgcolor: 'background.default', minHeight: '100vh' }}>
      <DeployKeyDialog
        t={t}
        open={open}
        setOpen={setOpen}
        connectionForm={connectionForm}
        setConnectionForm={setConnectionForm}
        hostError={hostError}
        setHostError={setHostError}
        pending={false}
        onDeploy={() => {}}
      />
    </Box>
  )
}

export const CustomDefaults: Story = {
  args: {
    initialForm: createConnectionForm(),
  },
}

export const HetznerDefaults: Story = {
  args: {
    initialForm: {
      ...createConnectionForm(),
      port: 23,
      use_sftp_mode: true,
      default_path: '/./borg-repository',
      ssh_path_prefix: '',
      mount_point: 'hetzner',
    },
  },
}
