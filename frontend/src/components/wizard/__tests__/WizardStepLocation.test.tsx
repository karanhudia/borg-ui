import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import WizardStepLocation from '../WizardStepLocation'

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

const mockRcloneRemotes = [
  {
    id: 10,
    name: 'prod-s3',
    provider: 's3',
    last_test_status: 'connected',
  },
]

describe('WizardStepLocation', () => {
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

    it('renders location selection cards', () => {
      render(
        <WizardStepLocation
          mode="create"
          data={defaultData}
          sshConnections={[]}
          rcloneRemotes={mockRcloneRemotes}
          rcloneStatus={{ available: true, version: 'rclone v1.66.0' }}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(screen.getByText('Borg UI Server')).toBeInTheDocument()
      expect(screen.getByText('Remote Client')).toBeInTheDocument()
      expect(screen.getByText('Cloud storage (rclone)')).toBeInTheDocument()
    })

    it('shows rclone remote controls and route preview when cloud storage is selected', () => {
      render(
        <WizardStepLocation
          mode="create"
          data={{
            ...defaultData,
            repositoryLocation: 'rclone',
            rcloneRemoteId: 10,
            rcloneRemotePath: 'borg-ui/repositories/app',
          }}
          sshConnections={[]}
          rcloneRemotes={mockRcloneRemotes}
          rcloneStatus={{ available: true, version: 'rclone v1.66.0' }}
          onChange={vi.fn()}
          onBrowsePath={vi.fn()}
        />
      )

      expect(screen.getByText('prod-s3')).toBeInTheDocument()
      expect(screen.getByLabelText(/Relative Remote Path/i)).toHaveValue('borg-ui/repositories/app')
      expect(
        screen.getByText(/Borg UI server -> local cache -> rclone sync -> remote/i)
      ).toBeInTheDocument()
    })

    it('keeps filesystem repository path separate when editing rclone remote path', () => {
      const onChange = vi.fn()

      render(
        <WizardStepLocation
          mode="create"
          data={{
            ...defaultData,
            repositoryLocation: 'rclone',
            path: '/backups/local-repo',
            rcloneRemoteId: 10,
            rcloneRemotePath: '',
          }}
          sshConnections={[]}
          rcloneRemotes={mockRcloneRemotes}
          rcloneStatus={{ available: true, version: 'rclone v1.66.0' }}
          onChange={onChange}
          onBrowsePath={vi.fn()}
        />
      )

      fireEvent.change(screen.getByLabelText(/Relative Remote Path/i), {
        target: { value: 'borg-ui/repositories/app' },
      })

      expect(onChange).toHaveBeenCalledWith({
        rcloneRemotePath: 'borg-ui/repositories/app',
      })
    })

    it('does not allow cloud storage selection when rclone is unavailable', () => {
      const onChange = vi.fn()

      render(
        <WizardStepLocation
          mode="create"
          data={defaultData}
          sshConnections={[]}
          rcloneRemotes={mockRcloneRemotes}
          rcloneStatus={{ available: false, error: 'rclone binary not found' }}
          onChange={onChange}
          onBrowsePath={vi.fn()}
        />
      )

      const rcloneCard = screen.getByText('Cloud storage (rclone)').closest('button')
      expect(rcloneCard).toBeDisabled()

      fireEvent.click(rcloneCard!)

      expect(onChange).not.toHaveBeenCalledWith(
        expect.objectContaining({ repositoryLocation: 'rclone' })
      )
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

  describe('Location Card Selection', () => {
    it('calls onChange when Borg UI Server is clicked', async () => {
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

      const localCard = screen.getByText('Borg UI Server').closest('button')
      await user.click(localCard!)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          repositoryLocation: 'local',
        })
      )
    })

    it('calls onChange when Remote Client is clicked', async () => {
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

      const remoteCard = screen.getByText('Remote Client').closest('button')
      await user.click(remoteCard!)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          repositoryLocation: 'ssh',
        })
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
