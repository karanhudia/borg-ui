import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, Mock, vi } from 'vitest'
import RepositoryWizard from '../RepositoryWizard'
import { managedAgentsAPI, sshKeysAPI } from '../../services/api'

const { mockTrack, mockTrackRepository } = vi.hoisted(() => ({
  mockTrack: vi.fn(),
  mockTrackRepository: vi.fn(),
}))

vi.mock('../../services/api', () => ({
  sshKeysAPI: {
    getSSHConnections: vi.fn(),
  },
  managedAgentsAPI: {
    listAgents: vi.fn(),
  },
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    track: mockTrack,
    trackRepository: mockTrackRepository,
    EventCategory: { REPOSITORY: 'repository' },
    EventAction: { CREATE: 'create', EDIT: 'edit', UPLOAD: 'upload' },
  }),
}))

vi.mock('../CompressionSettings', () => ({
  default: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => (
    <div data-testid="compression-settings">
      <span>Compression: {value}</span>
      <button onClick={() => onChange('zstd')}>Use zstd</button>
    </div>
  ),
}))

vi.mock('../CommandPreview', () => ({
  default: () => <div data-testid="command-preview">Command Preview</div>,
}))

vi.mock('../ExcludePatternInput', () => ({
  default: () => <div data-testid="exclude-patterns">Exclude Patterns</div>,
}))

vi.mock('../FileExplorerDialog', () => ({
  default: () => null,
}))

vi.mock('../AdvancedRepositoryOptions', () => ({
  default: ({
    remotePath,
    customFlags,
    onRemotePathChange,
    onCustomFlagsChange,
  }: {
    remotePath: string
    customFlags: string
    onRemotePathChange: (value: string) => void
    onCustomFlagsChange: (value: string) => void
  }) => (
    <div data-testid="advanced-options">
      <label htmlFor="remote-borg-path">Remote Borg Path</label>
      <input
        id="remote-borg-path"
        value={remotePath}
        onChange={(event) => onRemotePathChange(event.target.value)}
      />
      <label htmlFor="custom-borg-flags">Custom Borg Flags</label>
      <input
        id="custom-borg-flags"
        value={customFlags}
        onChange={(event) => onCustomFlagsChange(event.target.value)}
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
    default_path: '/data/backups',
    mount_point: null,
    status: 'disconnected',
  },
]

const mockManagedAgents = [
  {
    id: 101,
    name: 'workstation',
    agent_id: 'agent-workstation',
    hostname: 'workstation.local',
    status: 'online',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

const renderWizard = (
  mode: 'create' | 'import' | 'edit' = 'create',
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  repository?: any,
  onSubmit = vi.fn(),
  onClose = vi.fn()
) => {
  const queryClient = createQueryClient()
  return {
    ...render(
      <QueryClientProvider client={queryClient}>
        <RepositoryWizard
          open={true}
          onClose={onClose}
          mode={mode}
          repository={repository}
          onSubmit={onSubmit}
        />
      </QueryClientProvider>
    ),
    onSubmit,
    onClose,
  }
}

const setInputValue = (element: HTMLElement, value: string) => {
  fireEvent.change(element, { target: { value } })
}

const waitForLocationStep = async () => {
  await waitFor(() => {
    expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
  })
}

const fillLocalLocation = async (name = 'Test Repo', path = '/backups/test') => {
  await waitForLocationStep()
  setInputValue(screen.getByLabelText(/Repository Name/i), name)
  setInputValue(screen.getByLabelText(/Repository Path/i), path)
}

const chooseRemoteRepository = async (user: ReturnType<typeof userEvent.setup>) => {
  const remoteCard = screen.getByText('Remote Client').closest('button')
  await user.click(remoteCard!)

  await waitFor(() => {
    expect(screen.getAllByText('Select SSH Connection').length).toBeGreaterThanOrEqual(1)
  })

  const selectButtons = screen.getAllByRole('combobox')
  const selectButton = selectButtons[selectButtons.length - 1]
  await user.click(selectButton!)
  const listbox = await screen.findByRole('listbox')
  await user.click(within(listbox).getByText(/server1.example.com/i))
}

const advanceCreateToSecurity = async (user: ReturnType<typeof userEvent.setup>) => {
  await fillLocalLocation()
  await user.click(screen.getByRole('button', { name: /Next/i }))
  await waitFor(() => {
    expect(screen.getByText('Repository Key')).toBeInTheDocument()
  })
}

const advanceCreateToAdvanced = async (user: ReturnType<typeof userEvent.setup>) => {
  await advanceCreateToSecurity(user)
  setInputValue(screen.getByLabelText(/^Passphrase/i), 'testpass123')
  await user.click(screen.getByRole('button', { name: /Next/i }))
  await waitFor(() => {
    expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
  })
}

const advanceCreateToReview = async (user: ReturnType<typeof userEvent.setup>) => {
  await advanceCreateToAdvanced(user)
  await user.click(screen.getByRole('button', { name: /Next/i }))
  await waitFor(() => {
    expect(screen.getByRole('button', { name: /Create Repository/i })).toBeInTheDocument()
  })
}

const selectObserveMode = async (user: ReturnType<typeof userEvent.setup>) => {
  await waitForLocationStep()
  const selectButtons = screen.getAllByText('Full Repository')
  const selectButton =
    selectButtons.find((element) => element.closest('[role="combobox"]')) || selectButtons[0]
  await user.click(selectButton)
  const listbox = await screen.findByRole('listbox')
  await user.click(within(listbox).getByText('Observability Only'))
}

describe('RepositoryWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(sshKeysAPI.getSSHConnections as Mock).mockResolvedValue({
      data: { connections: mockSshConnections },
    })
    ;(managedAgentsAPI.listAgents as Mock).mockResolvedValue({
      data: mockManagedAgents,
    })
  })

  describe('create mode', () => {
    it('renders the current storage-target step flow', async () => {
      renderWizard('create')

      await waitFor(() => {
        expect(screen.getByText('Create Repository')).toBeInTheDocument()
        expect(screen.getByText('Location')).toBeInTheDocument()
      })

      expect(screen.getByText('Security')).toBeInTheDocument()
      expect(screen.getByText('Advanced')).toBeInTheDocument()
      expect(screen.getByText('Review')).toBeInTheDocument()
      expect(screen.queryByText('Source')).not.toBeInTheDocument()
      expect(screen.queryByText('Config')).not.toBeInTheDocument()
    })

    it('requires repository name and path before continuing', async () => {
      renderWizard('create')
      await waitForLocationStep()

      setInputValue(screen.getByLabelText(/Repository Path/i), '/backups/test')
      expect(screen.getByRole('button', { name: /Next/i })).toBeDisabled()

      setInputValue(screen.getByLabelText(/Repository Name/i), 'Test Repo')
      expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled()
    })

    it('requires an SSH connection for remote repositories', async () => {
      const user = userEvent.setup()
      renderWizard('create')
      await fillLocalLocation()

      const remoteCard = screen.getByText('Remote Client').closest('button')
      await user.click(remoteCard!)

      expect(screen.getByRole('button', { name: /Next/i })).toBeDisabled()
    })

    it('submits a local storage target without legacy backup sources', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('create')

      await advanceCreateToReview(user)
      await user.click(screen.getByRole('button', { name: /Create Repository/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Test Repo',
            path: '/backups/test',
            mode: 'full',
            connection_id: null,
            source_connection_id: null,
            source_directories: [],
            encryption: 'repokey',
            passphrase: 'testpass123',
            compression: 'lz4',
          }),
          null
        )
      })
    })

    it('submits a remote repository connection id', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('create')

      await fillLocalLocation('Remote Repo', '/offsite/repo')
      await chooseRemoteRepository(user)

      const pathInput = screen.getByLabelText(/Repository Path/i)
      await user.clear(pathInput)
      setInputValue(pathInput, '/offsite/repo')

      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Repository Key')).toBeInTheDocument()
      })
      setInputValue(screen.getByLabelText(/^Passphrase/i), 'securepass')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await user.click(screen.getByRole('button', { name: /Create Repository/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Remote Repo',
            path: '/offsite/repo',
            connection_id: 1,
            source_connection_id: null,
            source_directories: [],
            passphrase: 'securepass',
          }),
          null
        )
      })
    })

    it('submits managed-agent execution target fields', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('create')

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
      })

      setInputValue(screen.getByLabelText(/Repository Name/i), 'Agent Repo')
      setInputValue(screen.getByLabelText(/Repository Path/i), '/srv/borg/agent-repo')

      await user.click(screen.getByRole('button', { name: /Managed Agent/i }))

      expect(screen.getByRole('button', { name: /Next/i })).toBeDisabled()

      await user.click(screen.getByRole('combobox', { name: /Managed Agent/i }))
      const agentListbox = await screen.findByRole('listbox')
      await user.click(within(agentListbox).getByText('workstation.local'))

      expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled()
      await user.click(screen.getByRole('button', { name: /Next/i }))

      await waitFor(() => {
        expect(
          screen.getByText(/Source paths are resolved on the selected managed agent/i)
        ).toBeInTheDocument()
      })

      const dirInput = screen.getByPlaceholderText('/home/user/documents or /var/log/app.log')
      setInputValue(dirInput, '/home/user/data')
      await user.click(screen.getByRole('button', { name: /Add/i }))
      await user.click(screen.getByRole('button', { name: /Next/i }))

      await waitFor(() => {
        expect(screen.getByLabelText(/Remote Borg Path/i)).toBeInTheDocument()
      })
      setInputValue(screen.getByLabelText(/^Passphrase/i), 'agentpass')
      await user.click(screen.getByRole('button', { name: /Next/i }))

      await waitFor(() => {
        expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Create Repository/i })).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Create Repository/i }))

      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Agent Repo',
          path: '/srv/borg/agent-repo',
          execution_target: 'agent',
          agent_machine_id: 101,
          connection_id: null,
          source_connection_id: null,
          source_directories: ['/home/user/data'],
          passphrase: 'agentpass',
        }),
        null
      )
    })
  })

  describe('import mode', () => {
    it('shows the repository mode selector', async () => {
      renderWizard('import')

      await waitFor(() => {
        expect(screen.getByText('Import Repository')).toBeInTheDocument()
        expect(screen.getByText('Full Repository')).toBeInTheDocument()
      })
      expect(screen.getByText(/Create backups and browse archives/i)).toBeInTheDocument()
    })

    it('submits a full import without requiring source directories', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('import')

      await fillLocalLocation('Imported Repo', '/existing/repo')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Repository Key')).toBeInTheDocument()
      })

      expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled()
      setInputValue(screen.getByLabelText(/^Passphrase/i), 'importpass')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await user.click(screen.getByRole('button', { name: /Import Repository/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Imported Repo',
            path: '/existing/repo',
            mode: 'full',
            source_directories: [],
            source_connection_id: null,
            passphrase: 'importpass',
          }),
          null
        )
      })
    })

    it('passes an uploaded keyfile for keyfile-based imports and tracks upload analytics', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('import')

      await fillLocalLocation('Imported Keyfile Repo', '/existing/keyfile-repo')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByRole('combobox')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('combobox'))
      const listbox = await screen.findByRole('listbox')
      await user.click(within(listbox).getByText('Key File'))

      const uploadedKeyfile = new File(['BORG_KEY test'], 'imported.key', {
        type: 'application/octet-stream',
      })
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
      fireEvent.change(fileInput, { target: { files: [uploadedKeyfile] } })

      expect(await screen.findByText(/Keyfile will be uploaded after import/i)).toBeInTheDocument()
      setInputValue(screen.getByLabelText(/^Passphrase/i), 'importpass')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await user.click(screen.getByRole('button', { name: /Import Repository/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Imported Keyfile Repo',
            encryption: 'keyfile',
            passphrase: 'importpass',
          }),
          uploadedKeyfile
        )
      })
      expect(mockTrack).toHaveBeenCalledWith('repository', 'upload', {
        source: 'wizard',
        mode: 'import',
      })
      expect(mockTrackRepository).toHaveBeenCalledWith('upload', {
        name: 'Imported Keyfile Repo',
      })
    })

    it('submits observability-only imports with bypass lock', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('import')

      await selectObserveMode(user)
      await waitFor(() => {
        expect(screen.getByText(/Read-only storage access/i)).toBeInTheDocument()
      })
      await user.click(screen.getByRole('checkbox'))

      setInputValue(screen.getByLabelText(/Repository Name/i), 'Read Only Repo')
      setInputValue(screen.getByLabelText(/Repository Path/i), '/backup/readonly')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Repository Key')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await user.click(screen.getByRole('button', { name: /Import Repository/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Read Only Repo',
            path: '/backup/readonly',
            mode: 'observe',
            bypass_lock: true,
            source_directories: [],
          }),
          null
        )
      })
    })
  })

  describe('legacy edit mode', () => {
    const legacyRepository = {
      id: 7,
      name: 'Legacy Repo',
      path: '/backups/legacy',
      mode: 'full',
      source_directories: ['/data'],
      exclude_patterns: ['*.tmp'],
      source_ssh_connection_id: 1,
      custom_flags: '--stats',
      repository_type: 'local',
      encryption: 'repokey',
    }

    it('keeps source and config steps for existing repositories with legacy backup settings', async () => {
      renderWizard('edit', legacyRepository)

      await waitFor(() => {
        expect(screen.getByText('Edit Repository')).toBeInTheDocument()
        expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('Legacy Repo')
      })

      expect(screen.getByText('Source')).toBeInTheDocument()
      expect(screen.getByText('Config')).toBeInTheDocument()
      expect(screen.getByLabelText(/Repository Path/i)).toHaveValue('/backups/legacy')
    })

    it('allows edit workflow without re-entering the passphrase', async () => {
      const user = userEvent.setup()
      renderWizard('edit', legacyRepository)

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('Legacy Repo')
      })

      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText(/Where is the data you want to back up/i)).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText(/Encryption settings cannot be changed/i)).toBeInTheDocument()
      })

      expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled()
    })

    it('shows Save Changes on the final edit step', async () => {
      const user = userEvent.setup()
      renderWizard('edit', legacyRepository)

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('Legacy Repo')
      })

      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText(/Where is the data you want to back up/i)).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText(/Encryption settings cannot be changed/i)).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByTestId('advanced-options')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByTestId('exclude-patterns')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Save Changes/i })).toBeInTheDocument()
      })
    })
  })

  describe('SSH and loading behavior', () => {
    it('handles API errors when SSH connections cannot load', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      ;(sshKeysAPI.getSSHConnections as Mock).mockRejectedValue(new Error('Network Error'))
      const user = userEvent.setup()
      renderWizard('create')

      await waitFor(() => {
        expect(screen.getByText('Remote Client')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Remote Client').closest('button')!)

      await waitFor(() => {
        expect(screen.getByText(/No SSH connections configured/i)).toBeInTheDocument()
      })
      consoleSpy.mockRestore()
    })

    it('parses typed SSH repository URLs in create mode', async () => {
      const user = userEvent.setup()
      renderWizard('create')

      await waitForLocationStep()
      setInputValue(screen.getByLabelText(/Repository Name/i), 'Typed SSH Repo')
      const pathInput = screen.getByLabelText(/Repository Path/i)
      await user.clear(pathInput)
      setInputValue(pathInput, 'ssh://backupuser@server1.example.com:22/typed/repo')

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/\/path\/on\/remote\/server/i)).toBeInTheDocument()
        expect(screen.getByLabelText(/Repository Path/i)).toHaveValue('/typed/repo')
      })
      expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled()
    })
  })

  describe('navigation', () => {
    it('calls onClose from Cancel and disables Back on the first step', async () => {
      const user = userEvent.setup()
      const { onClose } = renderWizard('create')

      await waitForLocationStep()
      expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled()

      await user.click(screen.getByRole('button', { name: /Cancel/i }))
      expect(onClose).toHaveBeenCalled()
    })
  })
})
