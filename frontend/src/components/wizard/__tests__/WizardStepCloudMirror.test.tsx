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

  it('disables mirror enablement when the primary repository is not eligible', () => {
    render(
      <WizardStepCloudMirror
        data={defaultData}
        rcloneRemotes={remotes}
        rcloneStatus={{ available: true, version: 'rclone v1.66.0' }}
        eligible={false}
        primaryLocation="agent"
        onChange={vi.fn()}
        onAddRcloneRemote={vi.fn()}
        onBrowseRemotePath={vi.fn()}
      />
    )

    expect(screen.getByRole('checkbox', { name: /Mirror this repository/i })).toBeDisabled()
    expect(
      screen.getByText(/Managed-agent repositories need a separate mirror strategy/i)
    ).toBeInTheDocument()
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
      screen.getByText(/Borg UI server mounts the SSH repository via SSHFS/i)
    ).toBeInTheDocument()
    expect(screen.queryByText(/Local Cache Path/i)).not.toBeInTheDocument()
  })
})
