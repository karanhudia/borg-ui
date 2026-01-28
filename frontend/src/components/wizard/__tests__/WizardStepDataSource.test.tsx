import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import WizardStepDataSource from '../WizardStepDataSource'

// Mock SourceDirectoriesInput
vi.mock('../../SourceDirectoriesInput', () => ({
  default: ({
    directories,
    onChange,
    required,
  }: {
    directories: string[]
    onChange: (dirs: string[]) => void
    required: boolean
  }) => (
    <div data-testid="source-directories-input">
      <span>Source Directories {required ? '(required)' : '(optional)'}</span>
      <span>{directories.length} directories</span>
      <input
        placeholder="/home/user/documents"
        onChange={(e) => onChange([...directories, e.target.value])}
      />
    </div>
  ),
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
  dataSource: 'local' as const,
  sourceSshConnectionId: '' as number | '',
  sourceDirs: [] as string[],
}

describe('WizardStepDataSource', () => {
  describe('Rendering', () => {
    it('renders data source question', () => {
      render(
        <WizardStepDataSource
          repositoryLocation="local"
          repoSshConnectionId=""
          repositoryMode="full"
          data={defaultData}
          sshConnections={mockSshConnections}
          onChange={vi.fn()}
          onBrowseSource={vi.fn()}
          onBrowseRemoteSource={vi.fn()}
        />
      )

      expect(screen.getByText(/Where is the data you want to back up/i)).toBeInTheDocument()
    })

    it('renders Borg UI Server and Remote Client cards', () => {
      render(
        <WizardStepDataSource
          repositoryLocation="local"
          repoSshConnectionId=""
          repositoryMode="full"
          data={defaultData}
          sshConnections={mockSshConnections}
          onChange={vi.fn()}
          onBrowseSource={vi.fn()}
          onBrowseRemoteSource={vi.fn()}
        />
      )

      expect(screen.getByText('Borg UI Server')).toBeInTheDocument()
      expect(screen.getByText('Remote Client')).toBeInTheDocument()
    })

    it('renders source directories input when local is selected', () => {
      render(
        <WizardStepDataSource
          repositoryLocation="local"
          repoSshConnectionId=""
          repositoryMode="full"
          data={defaultData}
          sshConnections={mockSshConnections}
          onChange={vi.fn()}
          onBrowseSource={vi.fn()}
          onBrowseRemoteSource={vi.fn()}
        />
      )

      expect(screen.getByTestId('source-directories-input')).toBeInTheDocument()
    })
  })

  describe('Remote-to-Remote Blocking', () => {
    it('disables Remote Client card when repository is on SSH', () => {
      render(
        <WizardStepDataSource
          repositoryLocation="ssh"
          repoSshConnectionId={1}
          repositoryMode="full"
          data={defaultData}
          sshConnections={mockSshConnections}
          onChange={vi.fn()}
          onBrowseSource={vi.fn()}
          onBrowseRemoteSource={vi.fn()}
        />
      )

      // Should show explanation about why Remote Client is disabled
      expect(screen.getByText(/Why is "Remote Client" disabled/i)).toBeInTheDocument()
    })

    it('shows explanation alert when remote-to-remote is blocked', () => {
      render(
        <WizardStepDataSource
          repositoryLocation="ssh"
          repoSshConnectionId={1}
          repositoryMode="full"
          data={defaultData}
          sshConnections={mockSshConnections}
          onChange={vi.fn()}
          onBrowseSource={vi.fn()}
          onBrowseRemoteSource={vi.fn()}
        />
      )

      expect(screen.getByText(/Remote-to-remote backups are not supported/i)).toBeInTheDocument()
    })

    it('allows Remote Client when repository is local', () => {
      render(
        <WizardStepDataSource
          repositoryLocation="local"
          repoSshConnectionId=""
          repositoryMode="full"
          data={defaultData}
          sshConnections={mockSshConnections}
          onChange={vi.fn()}
          onBrowseSource={vi.fn()}
          onBrowseRemoteSource={vi.fn()}
        />
      )

      // Should NOT show the remote-to-remote warning
      expect(screen.queryByText(/Why is "Remote Client" disabled/i)).not.toBeInTheDocument()
    })
  })

  describe('Data Source Selection', () => {
    it('calls onChange when Borg UI Server is clicked', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      // Start with remote selected but no directories yet
      const remoteData = {
        ...defaultData,
        dataSource: 'remote' as const,
        sourceSshConnectionId: '' as number | '',
        sourceDirs: [],
      }

      render(
        <WizardStepDataSource
          repositoryLocation="local"
          repoSshConnectionId=""
          repositoryMode="full"
          data={remoteData}
          sshConnections={mockSshConnections}
          onChange={onChange}
          onBrowseSource={vi.fn()}
          onBrowseRemoteSource={vi.fn()}
        />
      )

      const localCard = screen.getByText('Borg UI Server').closest('button')
      await user.click(localCard!)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          dataSource: 'local',
        })
      )
    })

    it('calls onChange when Remote Client is clicked', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()

      render(
        <WizardStepDataSource
          repositoryLocation="local"
          repoSshConnectionId=""
          repositoryMode="full"
          data={defaultData}
          sshConnections={mockSshConnections}
          onChange={onChange}
          onBrowseSource={vi.fn()}
          onBrowseRemoteSource={vi.fn()}
        />
      )

      const remoteCard = screen.getByText('Remote Client').closest('button')
      await user.click(remoteCard!)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          dataSource: 'remote',
        })
      )
    })

    it('does NOT call onChange when clicking disabled Remote Client', () => {
      const onChange = vi.fn()

      render(
        <WizardStepDataSource
          repositoryLocation="ssh"
          repoSshConnectionId={1}
          repositoryMode="full"
          data={defaultData}
          sshConnections={mockSshConnections}
          onChange={onChange}
          onBrowseSource={vi.fn()}
          onBrowseRemoteSource={vi.fn()}
        />
      )

      // When disabled, the button has pointer-events: none
      // So we verify the button is disabled instead of clicking it
      const remoteCard = screen.getByText('Remote Client').closest('button')
      expect(remoteCard).toBeDisabled()
    })
  })

  describe('Source Directory Mutual Exclusion', () => {
    it('shows warning when local directories exist and trying to select remote', () => {
      const dataWithDirs = { ...defaultData, sourceDirs: ['/home/user'] }

      render(
        <WizardStepDataSource
          repositoryLocation="local"
          repoSshConnectionId=""
          repositoryMode="full"
          data={dataWithDirs}
          sshConnections={mockSshConnections}
          onChange={vi.fn()}
          onBrowseSource={vi.fn()}
          onBrowseRemoteSource={vi.fn()}
        />
      )

      expect(screen.getByText(/Remove local directories first to switch/i)).toBeInTheDocument()
    })

    it('shows warning when remote source is selected and trying to select local', () => {
      const remoteData = {
        dataSource: 'remote' as const,
        sourceSshConnectionId: 1,
        sourceDirs: ['/remote/dir'],
      }

      render(
        <WizardStepDataSource
          repositoryLocation="local"
          repoSshConnectionId=""
          repositoryMode="full"
          data={remoteData}
          sshConnections={mockSshConnections}
          onChange={vi.fn()}
          onBrowseSource={vi.fn()}
          onBrowseRemoteSource={vi.fn()}
        />
      )

      expect(screen.getByText(/Remove remote directories first to switch/i)).toBeInTheDocument()
    })
  })

  describe('Observe Mode', () => {
    it('shows source directories as optional in observe mode', () => {
      render(
        <WizardStepDataSource
          repositoryLocation="local"
          repoSshConnectionId=""
          repositoryMode="observe"
          data={defaultData}
          sshConnections={mockSshConnections}
          onChange={vi.fn()}
          onBrowseSource={vi.fn()}
          onBrowseRemoteSource={vi.fn()}
        />
      )

      expect(screen.getByText(/\(optional\)/i)).toBeInTheDocument()
    })

    it('shows source directories as required in full mode', () => {
      render(
        <WizardStepDataSource
          repositoryLocation="local"
          repoSshConnectionId=""
          repositoryMode="full"
          data={defaultData}
          sshConnections={mockSshConnections}
          onChange={vi.fn()}
          onBrowseSource={vi.fn()}
          onBrowseRemoteSource={vi.fn()}
        />
      )

      expect(screen.getByText(/\(required\)/i)).toBeInTheDocument()
    })
  })

  describe('Remote Source Configuration', () => {
    it('shows SSH connection dropdown when remote is selected', () => {
      const remoteData = { ...defaultData, dataSource: 'remote' as const }

      render(
        <WizardStepDataSource
          repositoryLocation="local"
          repoSshConnectionId=""
          repositoryMode="full"
          data={remoteData}
          sshConnections={mockSshConnections}
          onChange={vi.fn()}
          onBrowseSource={vi.fn()}
          onBrowseRemoteSource={vi.fn()}
        />
      )

      // MUI Select creates an InputLabel and a notched outline label
      const clientLabels = screen.getAllByText('Select Remote Client')
      expect(clientLabels.length).toBeGreaterThanOrEqual(1)
    })

    it('shows warning when no SSH connections available for remote source', () => {
      const remoteData = { ...defaultData, dataSource: 'remote' as const }

      render(
        <WizardStepDataSource
          repositoryLocation="local"
          repoSshConnectionId=""
          repositoryMode="full"
          data={remoteData}
          sshConnections={[]}
          onChange={vi.fn()}
          onBrowseSource={vi.fn()}
          onBrowseRemoteSource={vi.fn()}
        />
      )

      expect(screen.getByText(/No SSH connections configured/i)).toBeInTheDocument()
    })
  })
})
