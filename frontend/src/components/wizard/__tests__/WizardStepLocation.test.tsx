import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import WizardStepLocation from '../WizardStepLocation'
import { fullFeatureSystemInfo } from '../WizardStepLocation.storyFixtures'

vi.mock('../../../hooks/usePlan', () => ({
  usePlan: () => ({ plan: 'community', features: {}, isLoading: false, can: () => true }),
}))

const mockSshConnections = [
  {
    id: 1,
    host: 'server1.example.com',
    username: 'backupuser',
    port: 22,
    ssh_key_id: 1,
    default_path: '/backups',
    mount_point: '/mnt/server1',
    status: 'connected',
  },
  {
    id: 2,
    host: 'server2.example.com',
    username: 'admin',
    port: 2222,
    ssh_key_id: 2,
    default_path: '/data',
    mount_point: undefined,
    status: 'disconnected',
  },
]

const mockRcloneRemotes = [
  {
    id: 10,
    name: 'prod-s3',
    provider: 's3',
    last_test_status: 'connected',
  },
]

const defaultData = {
  name: '',
  repositoryMode: 'full' as const,
  repositoryLocation: 'local' as const,
  path: '',
  repoSshConnectionId: '' as number | '',
  bypassLock: false,
  rcloneRemoteId: '' as number | '',
  rcloneRemotePath: '',
  rcloneSyncPolicy: 'after_success' as const,
  rcloneExtraFlags: '',
}

const openDestinationSelect = async (user: ReturnType<typeof userEvent.setup>) => {
  const combobox = screen.getByRole('combobox', { name: /Where should backups be stored/i })
  await user.click(combobox)
}

describe('WizardStepLocation', () => {
  it('seeds Storybook with Borg v2 access so visual snapshots keep the version selector', () => {
    expect(fullFeatureSystemInfo.feature_access.borg_v2).toBe(true)
  })

  describe('Create Mode', () => {
    it('renders Repository Name input', () => {
      render(
        <WizardStepLocation
          mode="create"
          data={defaultData}
          sshConnections={[]}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
    })

    it('renders Repository Path input', () => {
      render(
        <WizardStepLocation
          mode="create"
          data={defaultData}
          sshConnections={[]}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(screen.getByLabelText(/Repository Path/i)).toBeInTheDocument()
    })

    it('renders destination Select with the three primary destinations', async () => {
      const user = userEvent.setup()
      render(
        <WizardStepLocation
          mode="create"
          data={defaultData}
          sshConnections={[]}
          agentMachines={[
            { id: 101, name: 'Workstation', hostname: 'workstation.local', status: 'online' },
          ]}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(
        screen.getByRole('combobox', { name: /Where should backups be stored/i })
      ).toBeInTheDocument()

      await openDestinationSelect(user)
      const listbox = await screen.findByRole('listbox')
      expect(within(listbox).getByRole('option', { name: /Borg UI Server/i })).toBeInTheDocument()
      expect(within(listbox).getByRole('option', { name: /Remote Client/i })).toBeInTheDocument()
      expect(within(listbox).getByRole('option', { name: /Managed Agent/i })).toBeInTheDocument()
      expect(
        within(listbox).queryByRole('option', { name: /Cloud Storage/i })
      ).not.toBeInTheDocument()
    })

    it('does NOT show Repository Mode selector in create mode', () => {
      render(
        <WizardStepLocation
          mode="create"
          data={defaultData}
          sshConnections={[]}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(screen.queryByLabelText(/Repository Mode/i)).not.toBeInTheDocument()
    })

    it('calls onChange when name is entered', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()

      render(
        <WizardStepLocation
          mode="create"
          data={defaultData}
          sshConnections={[]}
          onChange={onChange}
          onBrowsePath={vi.fn()}
        />
      )

      await user.type(screen.getByLabelText(/Repository Name/i), 'My Repo')

      expect(onChange).toHaveBeenCalled()
    })

    it('calls onChange when path is entered', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()

      render(
        <WizardStepLocation
          mode="create"
          data={defaultData}
          sshConnections={[]}
          onChange={onChange}
          onBrowsePath={vi.fn()}
        />
      )

      await user.type(screen.getByLabelText(/Repository Path/i), '/backups/test')

      expect(onChange).toHaveBeenCalled()
    })

    it('calls onBrowsePath when browse button is clicked', async () => {
      const user = userEvent.setup()
      const onBrowsePath = vi.fn()

      render(
        <WizardStepLocation
          mode="create"
          data={defaultData}
          sshConnections={[]}
          onChange={vi.fn()}
          onBrowsePath={onBrowsePath}
        />
      )

      const browseButton = screen.getByRole('button', { name: /Browse filesystem/i })
      await user.click(browseButton)

      expect(onBrowsePath).toHaveBeenCalled()
    })

    it('shows Borg 2 beta as tooltip affordance without inline alert', () => {
      render(
        <WizardStepLocation
          mode="create"
          data={{ ...defaultData, borgVersion: 2 }}
          sshConnections={[]}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(screen.getByText('Beta')).toBeInTheDocument()
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })

    it('shows direct Borg 2 rclone as an advanced option and hides the destination Select', () => {
      render(
        <WizardStepLocation
          mode="create"
          data={{ ...defaultData, borgVersion: 2 }}
          sshConnections={[]}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(screen.getByText('Advanced storage mode')).toBeInTheDocument()
      expect(
        screen.getByRole('checkbox', { name: /Use direct Borg 2 rclone repository/i })
      ).toBeInTheDocument()
    })

    it('hides destination Select when direct rclone is active', () => {
      render(
        <WizardStepLocation
          mode="create"
          data={{
            ...defaultData,
            borgVersion: 2,
            repositoryLocation: 'rclone',
            path: 'rclone://prod-s3/borg-ui/direct',
          }}
          sshConnections={[]}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(
        screen.queryByRole('combobox', { name: /Where should backups be stored/i })
      ).not.toBeInTheDocument()
    })

    it('shows direct rclone URL field with correct labels in direct mode', () => {
      render(
        <WizardStepLocation
          mode="create"
          data={{
            ...defaultData,
            borgVersion: 2,
            repositoryLocation: 'rclone',
            path: 'rclone://prod-s3/borg-ui/direct',
          }}
          sshConnections={[]}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(screen.getByLabelText(/Direct rclone repository URL/i)).toBeInTheDocument()
      expect(
        screen.getByPlaceholderText(/rclone:\/\/remote-name\/path\/to\/repository/i)
      ).toBeInTheDocument()
      expect(screen.getByText(/Borg writes directly through rclone/i)).toBeInTheDocument()
    })

    it('enables rclone browsing when connected storage is selected in direct mode', async () => {
      const user = userEvent.setup()
      const onBrowseDirectRclonePath = vi.fn()

      render(
        <WizardStepLocation
          mode="create"
          data={{
            ...defaultData,
            borgVersion: 2,
            repositoryLocation: 'rclone',
            rcloneRemoteId: 10,
            rcloneRemotePath: 'borg-ui/direct',
            path: 'rclone://prod-s3/borg-ui/direct',
          }}
          sshConnections={[]}
          rcloneStatus={{ available: true, version: 'rclone v1.66.0' }}
          rcloneRemotes={mockRcloneRemotes}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
          onBrowseDirectRclonePath={onBrowseDirectRclonePath}
        />
      )

      expect(screen.getByRole('combobox', { name: /Rclone Remote/i })).toHaveTextContent('prod-s3')
      expect(screen.getByLabelText(/Direct rclone repository URL/i)).toHaveValue(
        'rclone://prod-s3/borg-ui/direct'
      )

      const browseButton = screen.getByRole('button', { name: /Browse rclone remote/i })
      expect(browseButton).not.toBeDisabled()
      await user.click(browseButton)

      expect(onBrowseDirectRclonePath).toHaveBeenCalledTimes(1)
    })
  })

  describe('Import Mode', () => {
    it('shows Repository Mode selector', () => {
      render(
        <WizardStepLocation
          mode="import"
          data={defaultData}
          sshConnections={[]}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(screen.getByText('Full Repository')).toBeInTheDocument()
    })

    it('shows bypass lock checkbox when observe mode is selected', () => {
      const observeData = { ...defaultData, repositoryMode: 'observe' as const }

      render(
        <WizardStepLocation
          mode="import"
          data={observeData}
          sshConnections={[]}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(screen.getByText(/Read-only storage access/i)).toBeInTheDocument()
    })

    it('does NOT show bypass lock checkbox in full mode', () => {
      render(
        <WizardStepLocation
          mode="import"
          data={defaultData}
          sshConnections={[]}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(screen.queryByText(/Read-only storage access/i)).not.toBeInTheDocument()
    })
  })

  describe('Destination Selection', () => {
    it('calls onChange with local when Borg UI Server is selected', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      const sshData = { ...defaultData, repositoryLocation: 'ssh' as const }

      render(
        <WizardStepLocation
          mode="create"
          data={sshData}
          sshConnections={mockSshConnections}
          onChange={onChange}
          onBrowsePath={vi.fn()}
        />
      )

      await openDestinationSelect(user)
      const option = await screen.findByRole('option', { name: /Borg UI Server/i })
      await user.click(option)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          repositoryLocation: 'local',
        })
      )
    })

    it('calls onChange with ssh when Remote Client is selected', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()

      render(
        <WizardStepLocation
          mode="create"
          data={defaultData}
          sshConnections={mockSshConnections}
          onChange={onChange}
          onBrowsePath={vi.fn()}
        />
      )

      await openDestinationSelect(user)
      const option = await screen.findByRole('option', { name: /Remote Client/i })
      await user.click(option)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          repositoryLocation: 'ssh',
        })
      )
    })

    it('calls onChange with agent execution target when Managed Agent is selected', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()

      render(
        <WizardStepLocation
          mode="create"
          data={defaultData}
          sshConnections={[]}
          agentMachines={[
            { id: 7, name: 'Workstation', hostname: 'workstation.local', status: 'online' },
          ]}
          onChange={onChange}
          onBrowsePath={vi.fn()}
        />
      )

      await openDestinationSelect(user)
      const option = await screen.findByRole('option', { name: /Managed Agent/i })
      await user.click(option)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          executionTarget: 'agent',
        })
      )
    })

    it('disables managed-agent destination when the plan cannot use managed agents', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()

      render(
        <WizardStepLocation
          mode="create"
          data={defaultData}
          sshConnections={[]}
          agentMachines={[
            { id: 7, name: 'Workstation', hostname: 'workstation.local', status: 'online' },
          ]}
          canUseManagedAgents={false}
          onChange={onChange}
          onBrowsePath={vi.fn()}
        />
      )

      await openDestinationSelect(user)
      const listbox = await screen.findByRole('listbox')
      const agentOption = within(listbox).getByRole('option', { name: /Managed Agent/i })

      expect(agentOption).toHaveAttribute('aria-disabled', 'true')
      fireEvent.click(agentOption)
      expect(onChange).not.toHaveBeenCalledWith(
        expect.objectContaining({
          executionTarget: 'agent',
        })
      )
    })
  })

  describe('Plan Gates', () => {
    it('disables direct rclone mode when the plan cannot use rclone', () => {
      const onChange = vi.fn()

      render(
        <WizardStepLocation
          mode="create"
          data={{ ...defaultData, borgVersion: 2 }}
          sshConnections={[]}
          canUseRclone={false}
          onChange={onChange}
          onBrowsePath={vi.fn()}
        />
      )

      const directRcloneToggle = screen.getByRole('checkbox', {
        name: /Use direct Borg 2 rclone repository/i,
      })

      expect(directRcloneToggle).toBeDisabled()
      fireEvent.click(directRcloneToggle)
      expect(onChange).not.toHaveBeenCalledWith(
        expect.objectContaining({ repositoryLocation: 'rclone' })
      )
    })
  })

  describe('SSH Connection Selection', () => {
    it('shows SSH connection dropdown when Remote Client is selected', () => {
      const sshData = { ...defaultData, repositoryLocation: 'ssh' as const }

      render(
        <WizardStepLocation
          mode="create"
          data={sshData}
          sshConnections={mockSshConnections}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      // MUI Select creates an InputLabel and a notched outline label
      const sshLabels = screen.getAllByText('Select SSH Connection')
      expect(sshLabels.length).toBeGreaterThanOrEqual(1)
    })

    it('shows warning when no SSH connections available', () => {
      const sshData = { ...defaultData, repositoryLocation: 'ssh' as const }

      render(
        <WizardStepLocation
          mode="create"
          data={sshData}
          sshConnections={[]}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(screen.getByText(/No SSH connections configured/i)).toBeInTheDocument()
    })

    it('disables browse button when Remote Client selected but no connection chosen', () => {
      const sshData = { ...defaultData, repositoryLocation: 'ssh' as const }

      render(
        <WizardStepLocation
          mode="create"
          data={sshData}
          sshConnections={mockSshConnections}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      const browseButton = screen.getByRole('button', { name: /Browse filesystem/i })
      expect(browseButton).toBeDisabled()
    })

    it('enables browse button when SSH connection is selected', () => {
      const sshData = {
        ...defaultData,
        repositoryLocation: 'ssh' as const,
        repoSshConnectionId: 1,
      }

      render(
        <WizardStepLocation
          mode="create"
          data={sshData}
          sshConnections={mockSshConnections}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      const browseButton = screen.getByRole('button', { name: /Browse filesystem/i })
      expect(browseButton).not.toBeDisabled()
    })
  })

  describe('Path Placeholder', () => {
    it('shows local path placeholder when Borg UI Server selected', () => {
      render(
        <WizardStepLocation
          mode="create"
          data={defaultData}
          sshConnections={[]}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(screen.getByPlaceholderText(/\/backups\/my-repo/i)).toBeInTheDocument()
    })

    it('shows remote path placeholder when Remote Client selected', () => {
      const sshData = { ...defaultData, repositoryLocation: 'ssh' as const }

      render(
        <WizardStepLocation
          mode="create"
          data={sshData}
          sshConnections={mockSshConnections}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(screen.getByPlaceholderText(/\/path\/on\/remote\/server/i)).toBeInTheDocument()
    })
  })
})
