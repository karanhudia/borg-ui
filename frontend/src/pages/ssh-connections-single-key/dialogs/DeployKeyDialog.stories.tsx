import { useState, type JSX } from 'react'
import type { TFunction } from 'i18next'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import i18n from '../../../i18n'
import { createConnectionForm } from '../formDefaults'
import type { DeployConnectionPayload, SSHKeySummary } from '../types'
import { DeployKeyDialog } from './DeployKeyDialog'

const t = i18n.t.bind(i18n) as TFunction

const systemKey: SSHKeySummary = {
  id: 1,
  name: 'System SSH Key',
  key_type: 'ed25519',
  fingerprint: 'SHA256:3b1f9c0d7a42e8b5',
  is_system_key: true,
  connection_count: 2,
}

const extraKey: SSHKeySummary = {
  id: 2,
  name: 'borgserver-repo1',
  key_type: 'ed25519',
  fingerprint: 'SHA256:9a77d1c4e0b2f6a8',
  is_system_key: false,
  connection_count: 0,
}

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
  sshKeys = [systemKey],
}: {
  initialForm: DeployConnectionPayload
  sshKeys?: SSHKeySummary[]
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
        sshKeys={sshKeys}
        systemKeyId={systemKey.id}
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

/** With an extra key, a picker appears; the system key stays preselected. */
export const WithKeyPicker: Story = {
  args: {
    initialForm: createConnectionForm(),
    sshKeys: [systemKey, extraKey],
  },
}

export const HetznerDefaults: Story = {
  args: {
    initialForm: {
      ...createConnectionForm(),
      port: 23,
      use_sftp_mode: true,
      default_path: '/home',
      ssh_path_prefix: '',
      mount_point: 'hetzner-storage-box',
    },
  },
}

export const PresetIconColors: Story = {
  args: {
    initialForm: {
      ...createConnectionForm(),
      port: 23,
      use_sftp_mode: true,
      default_path: '/home',
      ssh_path_prefix: '',
      mount_point: 'hetzner-storage-box',
    },
  },
}

export const RsyncNetDefaults: Story = {
  args: {
    initialForm: {
      ...createConnectionForm(),
      port: 22,
      use_sftp_mode: true,
      default_path: '/',
      ssh_path_prefix: '',
      mount_point: 'rsync-net',
    },
  },
}
