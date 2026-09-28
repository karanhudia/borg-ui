import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import WizardStepCloudMirror from '../WizardStepCloudMirror'

const remotes = [
  {
    id: 10,
    name: 'prod-s3',
    provider: 's3',
    last_test_status: 'connected',
  },
]

const defaultData = {
  cloudMirrorEnabled: false,
  rcloneRemoteId: '' as number | '',
  rcloneRemotePath: '',
  rcloneRemotePathVerified: false,
  rcloneSyncPolicy: 'after_success' as const,
  rcloneSyncCronExpression: '0 */6 * * *',
  rcloneSyncTimezone: 'UTC',
  rcloneExtraFlags: '',
}

describe('WizardStepCloudMirror', () => {
  it('is disabled by default and hides mirror controls', () => {
    render(
      <WizardStepCloudMirror
        data={defaultData}
        rcloneRemotes={remotes}
        rcloneStatus={{ available: true, version: 'rclone v1.66.0' }}
        eligible={true}
        onChange={vi.fn()}
        onAddRcloneRemote={vi.fn()}
        onBrowseRemotePath={vi.fn()}
      />
    )

    expect(screen.getByRole('checkbox', { name: /Mirror this repository/i })).not.toBeChecked()
    expect(screen.queryByRole('combobox', { name: /Rclone Remote/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/Local Cache Path/i)).not.toBeInTheDocument()
  })

  it('shows remote, relative path, sync policy, and extra flags when enabled', async () => {
    const onChange = vi.fn()
    const onBrowseRemotePath = vi.fn()
    const user = userEvent.setup()

    render(
      <WizardStepCloudMirror
        data={{ ...defaultData, cloudMirrorEnabled: true, rcloneRemoteId: 10 }}
        rcloneRemotes={remotes}
        rcloneStatus={{ available: true, version: 'rclone v1.66.0' }}
        eligible={true}
        onChange={onChange}
        onAddRcloneRemote={vi.fn()}
        onBrowseRemotePath={onBrowseRemotePath}
      />
    )

    expect(screen.getByRole('combobox', { name: /Rclone Remote/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/Relative Remote Path/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Sync Policy/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Extra rclone Flags/i)).toBeInTheDocument()
    expect(screen.queryByText(/Local Cache Path/i)).not.toBeInTheDocument()

    const remoteSelect = screen.getByRole('combobox', { name: /Rclone Remote/i })
    expect(remoteSelect).toHaveTextContent('prod-s3')
    expect(remoteSelect).toHaveTextContent('s3')
    expect(remoteSelect).toHaveTextContent('connected')

    fireEvent.change(screen.getByLabelText(/Relative Remote Path/i), {
      target: { value: 'borg-ui/repositories/app' },
    })

    expect(onChange).toHaveBeenCalledWith({
      rcloneRemotePath: 'borg-ui/repositories/app',
      rcloneRemotePathVerified: false,
    })

    await user.click(screen.getByRole('button', { name: /Browse rclone remote/i }))
    expect(onBrowseRemotePath).toHaveBeenCalledTimes(1)
  })

  it('shows cron and timezone fields for scheduled mirror syncs', () => {
    const onChange = vi.fn()

    render(
      <WizardStepCloudMirror
        data={{
          ...defaultData,
          cloudMirrorEnabled: true,
          rcloneRemoteId: 10,
          rcloneSyncPolicy: 'scheduled',
          rcloneSyncCronExpression: '15 */4 * * *',
          rcloneSyncTimezone: 'UTC',
        }}
        rcloneRemotes={remotes}
        rcloneStatus={{ available: true, version: 'rclone v1.66.0' }}
        eligible={true}
        onChange={onChange}
        onAddRcloneRemote={vi.fn()}
        onBrowseRemotePath={vi.fn()}
      />
    )

    expect(screen.getByLabelText(/Mirror schedule/i)).toHaveValue('15 */4 * * *')
    expect(screen.getByLabelText(/Timezone/i)).toHaveValue('UTC')
    expect(screen.getByLabelText(/Next 3 Run Times/i)).toBeInTheDocument()
    expect(
      screen.getAllByRole('button', { name: /Open schedule builder/i }).length
    ).toBeGreaterThan(0)

    fireEvent.change(screen.getByLabelText(/Mirror schedule/i), {
      target: { value: '*/30 * * * *' },
    })
    expect(onChange).toHaveBeenCalledWith({
      rcloneSyncCronExpression: '*/30 * * * *',
    })
  })

  it('uses the inline folder button to browse the selected remote path', async () => {
    const user = userEvent.setup()
    const onBrowseRemotePath = vi.fn()

    render(
      <WizardStepCloudMirror
        data={{
          ...defaultData,
          cloudMirrorEnabled: true,
          rcloneRemoteId: 10,
          rcloneRemotePath: 'borg-ui',
        }}
        rcloneRemotes={remotes}
        rcloneStatus={{ available: true, version: 'rclone v1.66.0' }}
        eligible={true}
        onChange={vi.fn()}
        onAddRcloneRemote={vi.fn()}
        onBrowseRemotePath={onBrowseRemotePath}
      />
    )

    await user.click(screen.getByRole('button', { name: /Browse rclone remote/i }))

    expect(onBrowseRemotePath).toHaveBeenCalled()
  })

  it('allows managed-agent-primary mirrors and explains the agent-owned sync route', () => {
    render(
      <WizardStepCloudMirror
        data={{ ...defaultData, cloudMirrorEnabled: true, rcloneRemoteId: 10 }}
        rcloneRemotes={remotes}
        rcloneStatus={{ available: true, version: 'rclone v1.66.0' }}
        eligible={true}
        primaryLocation="agent"
        onChange={vi.fn()}
        onAddRcloneRemote={vi.fn()}
        onBrowseRemotePath={vi.fn()}
      />
    )

    expect(screen.getByRole('checkbox', { name: /Mirror this repository/i })).not.toBeDisabled()
    expect(
      screen.getByText(/Selected managed agent syncs its repository path to the rclone remote/i)
    ).toBeInTheDocument()
    expect(screen.queryByText(/Local Cache Path/i)).not.toBeInTheDocument()
  })

  it('allows SSH-primary repositories and explains the server-owned mount route', () => {
    render(
      <WizardStepCloudMirror
        data={{ ...defaultData, cloudMirrorEnabled: true, rcloneRemoteId: 10 }}
        rcloneRemotes={remotes}
        rcloneStatus={{ available: true, version: 'rclone v1.66.0' }}
        eligible={true}
        primaryLocation="ssh"
        onChange={vi.fn()}
        onAddRcloneRemote={vi.fn()}
        onBrowseRemotePath={vi.fn()}
      />
    )

    expect(screen.getByRole('checkbox', { name: /Mirror this repository/i })).not.toBeDisabled()
    expect(
      screen.getByText(/Borg UI server mounts the SSH repository read-only via SSHFS/i)
    ).toBeInTheDocument()
    expect(screen.queryByText(/Local Cache Path/i)).not.toBeInTheDocument()
  })

  it('lets an SSH mirror pick a separate SFTP connection or fall back to the repository one', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    const sshConnections = [
      { id: 7, host: 'repo.example', username: 'borg', port: 22, status: 'connected' },
      { id: 8, host: 'repo.example', username: 'sftp', port: 22, status: 'connected' },
    ]

    render(
      <WizardStepCloudMirror
        data={{ ...defaultData, cloudMirrorEnabled: true, rcloneSftpConnectionId: 8 }}
        rcloneRemotes={remotes}
        sshConnections={sshConnections}
        rcloneStatus={{ available: true, version: 'rclone v1.66.0' }}
        eligible={true}
        primaryLocation="ssh"
        onChange={onChange}
      />
    )

    const select = screen.getByRole('combobox', { name: /SFTP connection for cloud sync/i })
    expect(select).toHaveTextContent('sftp@repo.example')

    await user.click(select)
    await user.click(await screen.findByRole('option', { name: /Same as repository connection/i }))
    expect(onChange).toHaveBeenLastCalledWith({ rcloneSftpConnectionId: '' })

    await user.click(select)
    await user.click(await screen.findByRole('option', { name: /borg@repo\.example/i }))
    expect(onChange).toHaveBeenLastCalledWith({ rcloneSftpConnectionId: 7 })
  })

  it('hides the SFTP connection field for non-SSH mirrors', () => {
    render(
      <WizardStepCloudMirror
        data={{ ...defaultData, cloudMirrorEnabled: true }}
        rcloneRemotes={remotes}
        sshConnections={[
          { id: 7, host: 'repo.example', username: 'borg', port: 22, status: 'connected' },
        ]}
        rcloneStatus={{ available: true, version: 'rclone v1.66.0' }}
        eligible={true}
        onChange={vi.fn()}
      />
    )

    expect(
      screen.queryByRole('combobox', { name: /SFTP connection for cloud sync/i })
    ).not.toBeInTheDocument()
  })
})
