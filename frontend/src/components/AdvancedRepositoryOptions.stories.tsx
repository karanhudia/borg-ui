import { useEffect, useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import MockAdapter from 'axios-mock-adapter'
import api from '../services/api'
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
  borgVersion = 1,
  repositoryPath,
}: {
  initialUploadRatelimitMb?: string
  borgVersion?: 1 | 2
  repositoryPath?: string
}) => {
  const [remotePath, setRemotePath] = useState('')
  const [customFlags, setCustomFlags] = useState('--stats')
  const [uploadRatelimitMb, setUploadRatelimitMb] = useState(initialUploadRatelimitMb)

  return (
    <Box sx={{ width: 560, maxWidth: 'calc(100vw - 32px)' }}>
      <AdvancedRepositoryOptions
        repositoryId={null}
        mode="full"
        borgVersion={borgVersion}
        repositoryPath={repositoryPath}
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

/** Borg 2 has no upload limit: the field is disabled and says why. */
export const Borg2WithoutUploadLimit: Story = {
  render: () => <AdvancedRepositoryOptionsPreview initialUploadRatelimitMb="1.5" borgVersion={2} />,
}

export const Borg2BehindRcloneUploadLimit: Story = {
  render: () => (
    <AdvancedRepositoryOptionsPreview
      initialUploadRatelimitMb="1.5"
      borgVersion={2}
      repositoryPath="rclone:b2-offsite:borg/archive"
    />
  ),
}

const AGENT_REPOSITORY_ID = 7

const agentHook = {
  id: 11,
  script_id: null,
  agent_script_name: 'backup-postgres',
  is_agent_script: true,
  script_name: 'backup-postgres',
  script_description: null,
  execution_order: 1,
  enabled: true,
  custom_timeout: 1800,
  custom_run_on: null,
  continue_on_error: false,
  skip_on_failure: false,
  default_timeout: 300,
  default_run_on: 'always',
  parameters: [],
  parameter_values: null,
}

// a library script assigned before the repository moved to an agent
const leftoverLibraryHook = {
  ...agentHook,
  id: 12,
  script_id: 4,
  agent_script_name: null,
  is_agent_script: false,
  script_name: 'start-database',
  custom_timeout: null,
}

const AgentRepositoryPreview = ({
  repositoryId = AGENT_REPOSITORY_ID,
  preBackupScript = '',
  agentOnline = true,
}: {
  repositoryId?: number | null
  preBackupScript?: string
  agentOnline?: boolean
}) => {
  const [pre, setPre] = useState(preBackupScript)
  // Installed before the scripts tab mounts, restored on unmount; anything
  // the story does not answer passes through.
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const mock = new MockAdapter(api, { onNoMatch: 'passthrough' })
    mock.onGet(`/repositories/${AGENT_REPOSITORY_ID}/scripts`).reply(200, {
      pre_backup: [agentHook],
      post_backup: [leftoverLibraryHook],
    })
    mock.onGet(`/repositories/${AGENT_REPOSITORY_ID}/agent-scripts`).reply(200, {
      scripts: agentOnline
        ? [
            { name: 'backup-postgres', description: 'pg_dumpall to /var/backups' },
            { name: 'stop-app', description: null },
          ]
        : [],
      agent_online: agentOnline,
    })
    setReady(true)
    return () => {
      setReady(false)
      mock.restore()
    }
  }, [agentOnline])
  if (!ready) return null
  return (
    <Box sx={{ width: 560, maxWidth: 'calc(100vw - 32px)' }}>
      <AdvancedRepositoryOptions
        repositoryId={repositoryId}
        mode="full"
        remotePath=""
        preBackupScript={pre}
        postBackupScript=""
        preHookTimeout={300}
        postHookTimeout={300}
        hookFailureMode="fail"
        customFlags=""
        uploadRatelimitMb=""
        onRemotePathChange={noop}
        onPreBackupScriptChange={setPre}
        onPostBackupScriptChange={noop}
        onPreHookTimeoutChange={noop}
        onPostHookTimeoutChange={noop}
        onHookFailureModeChange={noop}
        onCustomFlagsChange={noop}
        onUploadRatelimitMbChange={noop}
        agentRepository
      />
    </Box>
  )
}

/** A new agent repository: no inline script is offered, and agent scripts
 * are added once the repository exists. */
export const AgentRepositoryNew: Story = {
  render: () => <AgentRepositoryPreview repositoryId={null} />,
}

/** An agent repository with an agent hook, plus an inline script and a
 * library script from before that never run: both say so. */
export const AgentRepositoryWithHooks: Story = {
  render: () => <AgentRepositoryPreview preBackupScript="systemctl stop postgresql" />,
}

// Opens the pre-backup hook's assign dialog the way a user does, once the
// scripts tab has loaded its hooks (it enables Add then). The dialog renders
// in a portal outside the story canvas.
const openAssignDialog = async ({ canvasElement }: { canvasElement: HTMLElement }) => {
  for (let i = 0; i < 100 && !canvasElement.textContent?.includes('backup-postgres'); i++) {
    await new Promise((resolve) => window.setTimeout(resolve, 20))
  }
  Array.from(canvasElement.querySelectorAll('button'))
    .find((button) => button.textContent?.trim() === 'Add')
    ?.click()
}

/** Adding a hook offers the scripts the agent publishes. */
export const AgentScriptDialog: Story = {
  render: () => <AgentRepositoryPreview />,
  play: openAssignDialog,
}

/** The agent is offline: nothing to pick, and the dialog says why. */
export const AgentScriptDialogOffline: Story = {
  render: () => <AgentRepositoryPreview agentOnline={false} />,
  play: openAssignDialog,
}
