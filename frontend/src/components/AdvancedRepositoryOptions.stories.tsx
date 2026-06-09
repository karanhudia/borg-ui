import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import AdvancedRepositoryOptions from './AdvancedRepositoryOptions'

const noop = () => {}

const meta = {
  title: 'Components/AdvancedRepositoryOptions',
  component: AdvancedRepositoryOptions,
  parameters: {
    layout: 'centered',
  },
  args: {
    repositoryId: null,
    mode: 'full',
    remotePath: '',
    preBackupScript: '',
    postBackupScript: '',
    preHookTimeout: 300,
    postHookTimeout: 300,
    hookFailureMode: 'fail',
    customFlags: '',
    uploadRatelimitMb: '',
    onRemotePathChange: noop,
    onPreBackupScriptChange: noop,
    onPostBackupScriptChange: noop,
    onPreHookTimeoutChange: noop,
    onPostHookTimeoutChange: noop,
    onHookFailureModeChange: noop,
    onCustomFlagsChange: noop,
    onUploadRatelimitMbChange: noop,
  },
} satisfies Meta<typeof AdvancedRepositoryOptions>

export default meta

type Story = StoryObj<typeof meta>

const AdvancedRepositoryOptionsPreview = ({
  initialUploadRatelimitMb = '',
}: {
  initialUploadRatelimitMb?: string
}) => {
  const [remotePath, setRemotePath] = useState('')
  const [customFlags, setCustomFlags] = useState('--stats')
  const [uploadRatelimitMb, setUploadRatelimitMb] = useState(initialUploadRatelimitMb)

  return (
    <Box sx={{ width: 560, maxWidth: 'calc(100vw - 32px)' }}>
      <AdvancedRepositoryOptions
        repositoryId={null}
        mode="full"
        remotePath={remotePath}
        preBackupScript=""
        postBackupScript=""
        preHookTimeout={300}
        postHookTimeout={300}
        hookFailureMode="fail"
        customFlags={customFlags}
        uploadRatelimitMb={uploadRatelimitMb}
        onRemotePathChange={setRemotePath}
        onPreBackupScriptChange={noop}
        onPostBackupScriptChange={noop}
        onPreHookTimeoutChange={noop}
        onPostHookTimeoutChange={noop}
        onHookFailureModeChange={noop}
        onCustomFlagsChange={setCustomFlags}
        onUploadRatelimitMbChange={setUploadRatelimitMb}
      />
    </Box>
  )
}

export const Default: Story = {
  render: () => <AdvancedRepositoryOptionsPreview />,
}

export const WithUploadLimit: Story = {
  render: () => <AdvancedRepositoryOptionsPreview initialUploadRatelimitMb="1.5" />,
}
