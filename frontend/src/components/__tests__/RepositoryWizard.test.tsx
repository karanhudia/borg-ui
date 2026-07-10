import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, Mock, vi } from 'vitest'
import type { ComponentProps } from 'react'
import RepositoryWizard from '../RepositoryWizard'
import { managedAgentsAPI, rcloneAPI, sshKeysAPI } from '../../services/api'

const { mockTrack, mockTrackRepository } = vi.hoisted(() => ({
  mockTrack: vi.fn(),
  mockTrackRepository: vi.fn(),
}))

vi.setConfig({ testTimeout: 60000 })

vi.mock('../../services/api', () => ({
  sshKeysAPI: {
    getSSHConnections: vi.fn(),
  },
  managedAgentsAPI: {
    listAgents: vi.fn(),
    getRepositoryDefaults: vi.fn(),
  },
  rcloneAPI: {
    getStatus: vi.fn(),
    getProviders: vi.fn(),
    listRemotes: vi.fn(),
    createRemote: vi.fn(),
    browseRemote: vi.fn(),
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

vi.mock('../shared/CodeEditor', () => ({
  default: ({
    label,
    value,
    onChange,
  }: {
    label?: string
    value: string
    onChange: (value: string) => void
  }) => (
    <textarea aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} />
  ),
}))

vi.mock('../ExcludePatternInput', () => ({
  default: () => <div data-testid="exclude-patterns">Exclude Patterns</div>,
}))

vi.mock('../FileExplorerDialog', () => ({
  default: ({
    open,
    onSelect,
    connectionType,
    agentId,
    agentDefaultPath,
  }: {
    open: boolean
    onSelect: (paths: string[]) => void
    connectionType?: string
    agentId?: number
    agentDefaultPath?: string | null
  }) =>
    open ? (
      <div
        data-testid="file-explorer-dialog"
        data-connection-type={connectionType}
        data-agent-id={agentId || ''}
        data-agent-default-path={agentDefaultPath || ''}
      >
        <button
          type="button"
          onClick={() =>
            onSelect([
              connectionType === 'rclone' ? 'borg-ui/repositories' : '/selected/from-browser',
            ])
          }
        >
          Select browsed path
        </button>
      </div>
    ) : null,
}))

vi.mock('../AdvancedRepositoryOptions', () => ({
  default: ({
    remotePath,
    customFlags,
    uploadRatelimitMb = '',
    onRemotePathChange,
    onCustomFlagsChange,
    onUploadRatelimitMbChange = () => {},
  }: {
    remotePath: string
    customFlags: string
    uploadRatelimitMb?: string
    onRemotePathChange: (value: string) => void
    onCustomFlagsChange: (value: string) => void
    onUploadRatelimitMbChange?: (value: string) => void
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
      <label htmlFor="upload-speed-limit">Upload speed limit</label>
      <input
        id="upload-speed-limit"
        value={uploadRatelimitMb}
        onChange={(event) => onUploadRatelimitMbChange(event.target.value)}
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
    default_path: '/home/workstation',
    status: 'online',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
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

const mockRcloneProviders = [
  {
    type: 'local',
    label: 'Local filesystem',
    description: 'Local path remote.',
    auth_type: 'none',
    type_editable: false,
    docs_url: 'https://rclone.org/local/',
    config_template: { type: 'local' },
    fields: [],
  },
  {
    type: 's3',
    label: 'Amazon S3 / S3-compatible',
    description: 'AWS S3, MinIO, Wasabi, Cloudflare R2, and compatible object stores.',
    auth_type: 'access_key',
    type_editable: false,
    docs_url: 'https://rclone.org/s3/',
    config_template: {
      type: 's3',
      provider: 'AWS',
      access_key_id: '',
      secret_access_key: '',
      region: '',
      endpoint: '',
    },
    fields: [],
  },
  {
    type: 'custom',
    label: 'Custom rclone backend',
    description: 'Manual setup for any rclone backend.',
    auth_type: 'manual',
    type_editable: true,
    docs_url: 'https://rclone.org/docs/',
    config_template: { type: '' },
    fields: [],
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
  onClose = vi.fn(),
  wizardProps: Partial<ComponentProps<typeof RepositoryWizard>> = {}
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
          {...wizardProps}
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

// The destination picker became a single MUI Select in commit f084508e
// (Borg UI Server / Remote Client / Managed Agent as options instead of card
// buttons). All higher-level wizard tests now drive it through this helper.
const chooseDestination = async (user: ReturnType<typeof userEvent.setup>, optionLabel: RegExp) => {
  const destinationSelect = screen.getByRole('combobox', {
    name: /Where should backups be stored/i,
  })
  await user.click(destinationSelect)
  const option = await screen.findByRole('option', { name: optionLabel })
  await user.click(option)
  await waitFor(() => {
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
}

const chooseRemoteRepository = async (user: ReturnType<typeof userEvent.setup>) => {
  await chooseDestination(user, /Remote Client/i)

  await waitFor(() => {
    expect(screen.getAllByText('Select SSH Connection').length).toBeGreaterThanOrEqual(1)
  })

  // After the destination Select closes, the SSH sub-form mounts. The SSH
  // Select doesn't have an explicit labelId so its accessible name isn't
  // always picked up by getByRole — fall back to finding the last combobox
  // on the page (destination is first, SSH is last).
  const comboboxes = screen.getAllByRole('combobox')
  await user.click(comboboxes[comboboxes.length - 1])
  const listbox = await screen.findByRole('listbox')
  await user.click(within(listbox).getByText(/server1.example.com/i))
}

const advanceCreateToSecurity = async (user: ReturnType<typeof userEvent.setup>) => {
  await fillLocalLocation()
  await user.click(screen.getByRole('button', { name: /Next/i }))
  await waitFor(() => {
    expect(screen.getByText('Mirror this repository to cloud storage')).toBeInTheDocument()
  })
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
    ;(managedAgentsAPI.getRepositoryDefaults as Mock).mockResolvedValue({
      data: { repo: null, remote_path: null, has_passphrase: false },
    })
    ;(rcloneAPI.getStatus as Mock).mockResolvedValue({
      data: { available: true, version: 'rclone v1.66.0', error: null },
    })
    ;(rcloneAPI.getProviders as Mock).mockResolvedValue({
      data: { providers: mockRcloneProviders },
    })
    ;(rcloneAPI.listRemotes as Mock).mockResolvedValue({
      data: { remotes: mockRcloneRemotes },
    })
    ;(rcloneAPI.createRemote as Mock).mockResolvedValue({
      data: { id: 42, name: 'local-test', provider: 'local', last_test_status: null },
    })
    ;(rcloneAPI.browseRemote as Mock).mockResolvedValue({
      data: {
        remote_id: 10,
        path: '',
        entries: [{ name: 'repositories', path: 'borg-ui/repositories', is_dir: true }],
      },
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
      expect(screen.getByText('Cloud Mirror')).toBeInTheDocument()
      expect(screen.getByText('Advanced')).toBeInTheDocument()
      expect(screen.getByText('Review')).toBeInTheDocument()
      expect(screen.queryByText('Source')).not.toBeInTheDocument()
      expect(screen.queryByText('Config')).not.toBeInTheDocument()
    })

    it('keeps Cloud Mirror immediately after Location when legacy source settings are shown', async () => {
      renderWizard('edit', {
        id: 1,
        name: 'Existing Repo',
        path: '/backups/existing',
        encryption: 'repokey',
        compression: 'lz4',
        mode: 'full',
        source_directories: ['/srv/app'],
        exclude_patterns: [],
      })

      await waitFor(() => {
        expect(screen.getByText('Location')).toBeInTheDocument()
      })

      const locationStep = screen.getByText('Location')
      const cloudMirrorStep = screen.getByText('Cloud Mirror')
      const sourceStep = screen.getByText('Source')

      expect(
        locationStep.compareDocumentPosition(cloudMirrorStep) & Node.DOCUMENT_POSITION_FOLLOWING
      ).toBeTruthy()
      expect(
        cloudMirrorStep.compareDocumentPosition(sourceStep) & Node.DOCUMENT_POSITION_FOLLOWING
      ).toBeTruthy()
    })

    it('preserves an agent repository ssh:// URL in edit mode (does not chop it to the path)', async () => {
      const agentRepoUrl = 'ssh://u209739@borg01.ioanalytica.com:23/./m3s/k8s-borg-m3s'
      // The agent still advertises the same repo; edit must show the full URL and
      // must not overwrite it with the advertised value (only-fill-if-empty guard).
      ;(managedAgentsAPI.getRepositoryDefaults as Mock).mockResolvedValue({
        data: { repo: agentRepoUrl, remote_path: null, has_passphrase: false },
      })

      renderWizard('edit', {
        id: 7,
        name: 'Agent Repo',
        path: agentRepoUrl,
        executor_type: 'agent',
        agent_machine_id: 101,
        encryption: 'repokey',
        compression: 'lz4',
        mode: 'full',
      })

      await waitForLocationStep()
      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Path/i)).toHaveValue(agentRepoUrl)
      })
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

      await chooseDestination(user, /Remote Client/i)

      expect(screen.getByRole('button', { name: /Next/i })).toBeDisabled()
    })

    it('disables paid repository destinations when plan features are unavailable', async () => {
      const user = userEvent.setup()
      renderWizard('create', undefined, vi.fn(), vi.fn(), {
        canUseManagedAgents: false,
        canUseRclone: false,
      })

      await waitForLocationStep()
      const destinationSelect = screen.getByRole('combobox', {
        name: /Where should backups be stored/i,
      })
      await user.click(destinationSelect)
      const listbox = await screen.findByRole('listbox')
      expect(within(listbox).getByRole('option', { name: /Managed Agent/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )

      await user.keyboard('{Escape}')
      await user.click(screen.getByRole('button', { name: /v2/i }))
      const directRcloneToggle = await screen.findByRole('checkbox', {
        name: /Use direct Borg 2 rclone repository/i,
      })
      expect(directRcloneToggle).toBeDisabled()
    }, 60000)

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
            storage_backend: 'local',
            cloud_mirror_enabled: false,
            rclone_remote_id: null,
            rclone_remote_path: null,
            rclone_remote_path_verified: false,
            rclone_extra_flags: [],
          }),
          null
        )
      })
    })

    it('submits upload speed limits in KiB per second', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('create')

      await advanceCreateToAdvanced(user)
      setInputValue(screen.getByLabelText(/Upload speed limit/i), '1.5')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Create Repository/i })).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Create Repository/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            upload_ratelimit_kib: 1536,
          }),
          null
        )
      })
    })

    it('submits direct Borg 2 rclone repositories through the advanced mode', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('create')

      await waitForLocationStep()
      await user.click(screen.getByRole('button', { name: /v2/i }))
      await user.click(
        await screen.findByRole('checkbox', { name: /Use direct Borg 2 rclone repository/i })
      )
      setInputValue(screen.getByLabelText(/Repository Name/i), 'Direct Cloud Repo')
      setInputValue(
        screen.getByLabelText(/Direct rclone repository URL/i),
        'rclone://prod-s3/borg-ui/direct'
      )

      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(
          screen.queryByText('Mirror this repository to cloud storage')
        ).not.toBeInTheDocument()
        expect(screen.getByLabelText(/^Passphrase/i)).toBeInTheDocument()
      })
      setInputValue(screen.getByLabelText(/^Passphrase/i), 'directpass')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Direct Borg 2 rclone')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Create Repository/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Direct Cloud Repo',
            borg_version: 2,
            path: 'rclone://prod-s3/borg-ui/direct',
            storage_backend: 'rclone_direct',
            execution_target: 'local',
            executor_type: 'server',
            connection_id: null,
            cloud_mirror_enabled: false,
            rclone_remote_id: null,
            rclone_remote_path: null,
            rclone_remote_path_verified: false,
            rclone_extra_flags: [],
          }),
          null
        )
      })
    }, 90000)

    it('composes direct Borg 2 rclone URLs from selected connected storage and browsed folders', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('create')
      ;(rcloneAPI.browseRemote as Mock)
        .mockResolvedValueOnce({
          data: {
            remote_id: 10,
            path: '',
            entries: [{ name: 'repositories', path: 'borg-ui/repositories', is_dir: true }],
          },
        })
        .mockResolvedValueOnce({
          data: {
            remote_id: 10,
            path: 'borg-ui/repositories',
            entries: [],
          },
        })

      await waitForLocationStep()
      await user.click(screen.getByRole('button', { name: /v2/i }))
      await user.click(
        await screen.findByRole('checkbox', { name: /Use direct Borg 2 rclone repository/i })
      )
      setInputValue(screen.getByLabelText(/Repository Name/i), 'Browsed Direct Cloud Repo')

      await user.click(await screen.findByRole('combobox', { name: /Rclone Remote/i }))
      const remoteListbox = await screen.findByRole('listbox')
      await user.click(within(remoteListbox).getByText('prod-s3'))

      expect(screen.getByLabelText(/Direct rclone repository URL/i)).toHaveValue(
        'rclone://prod-s3/'
      )

      await user.click(screen.getByRole('button', { name: /Browse rclone remote/i }))
      const fileExplorerDialog = await screen.findByTestId('file-explorer-dialog')
      expect(fileExplorerDialog).toHaveAttribute('data-connection-type', 'rclone')
      await user.click(
        within(fileExplorerDialog).getByRole('button', {
          name: /Select browsed path/i,
          hidden: true,
        })
      )

      expect(screen.getByLabelText(/Direct rclone repository URL/i)).toHaveValue(
        'rclone://prod-s3/borg-ui/repositories'
      )

      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByLabelText(/^Passphrase/i)).toBeInTheDocument()
      })
      setInputValue(screen.getByLabelText(/^Passphrase/i), 'directpass')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await user.click(screen.getByRole('button', { name: /Create Repository/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Browsed Direct Cloud Repo',
            borg_version: 2,
            path: 'rclone://prod-s3/borg-ui/repositories',
            storage_backend: 'rclone_direct',
            cloud_mirror_enabled: false,
            rclone_remote_id: null,
            rclone_remote_path: null,
            rclone_remote_path_verified: false,
          }),
          null
        )
      })
    }, 90000)

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
        expect(screen.getByText('Mirror this repository to cloud storage')).toBeInTheDocument()
      })
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
            storage_backend: 'ssh',
            connection_id: 1,
            source_connection_id: null,
            source_directories: [],
            passphrase: 'securepass',
          }),
          null
        )
      })
    })

    it('submits managed-agent execution target fields without repository source paths', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('create')

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
      })
      expect(screen.queryByText('Source')).not.toBeInTheDocument()

      setInputValue(screen.getByLabelText(/Repository Name/i), 'Agent Repo')
      setInputValue(screen.getByLabelText(/Repository Path/i), '/srv/borg/agent-repo')

      await chooseDestination(user, /Managed Agent/i)

      expect(screen.getByRole('button', { name: /Next/i })).toBeDisabled()

      await user.click(screen.getByRole('combobox', { name: /Managed Agent/i }))
      const agentListbox = await screen.findByRole('listbox')
      await user.click(within(agentListbox).getByText('workstation.local'))

      expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled()
      await user.click(screen.getByRole('button', { name: /Next/i }))

      await waitFor(() => {
        expect(screen.getByText('Mirror this repository to cloud storage')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))

      await waitFor(() => {
        expect(screen.getByText('Repository Key')).toBeInTheDocument()
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
          executor_type: 'agent',
          execution_target: 'agent',
          storage_backend: 'agent_local',
          agent_machine_id: 101,
          connection_id: null,
          source_connection_id: null,
          source_directories: [],
          source_locations: [],
          passphrase: 'agentpass',
        }),
        null
      )
    }, 90000)

    it('submits optional cloud mirror fields without changing the primary location', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('create')

      await fillLocalLocation('Cloud Repo', '/backups/cloud-repo')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Mirror this repository to cloud storage')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('checkbox', { name: /Mirror this repository/i }))

      await user.click(screen.getByRole('combobox', { name: /Rclone Remote/i }))
      const remoteListbox = await screen.findByRole('listbox')
      await user.click(within(remoteListbox).getByText('prod-s3'))
      setInputValue(screen.getByLabelText(/Relative Remote Path/i), 'borg-ui/repositories/app')

      expect(screen.queryByText(/Local Cache Path/i)).not.toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Repository Key')).toBeInTheDocument()
      })
      setInputValue(screen.getByLabelText(/^Passphrase/i), 'cloudpass')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await user.click(screen.getByRole('button', { name: /Create Repository/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Cloud Repo',
            storage_backend: 'local',
            cloud_mirror_enabled: true,
            rclone_remote_id: 10,
            rclone_remote_path: 'borg-ui/repositories/app',
            rclone_remote_path_verified: false,
            rclone_sync_policy: 'after_success',
            path: '/backups/cloud-repo',
            connection_id: null,
          }),
          null
        )
      })
    }, 90000)

    it('submits scheduled cloud mirror policy fields', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('create')

      await fillLocalLocation('Scheduled Cloud Repo', '/backups/scheduled-cloud')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Mirror this repository to cloud storage')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('checkbox', { name: /Mirror this repository/i }))

      await user.click(screen.getByRole('combobox', { name: /Rclone Remote/i }))
      const remoteListbox = await screen.findByRole('listbox')
      await user.click(within(remoteListbox).getByText('prod-s3'))
      setInputValue(
        screen.getByLabelText(/Relative Remote Path/i),
        'borg-ui/repositories/scheduled'
      )

      await user.click(screen.getByRole('combobox', { name: /Sync Policy/i }))
      const policyListbox = await screen.findByRole('listbox')
      await user.click(within(policyListbox).getByText('Scheduled sync'))
      setInputValue(screen.getByLabelText(/Mirror schedule/i), '*/30 * * * *')
      setInputValue(screen.getByLabelText(/Timezone/i), 'UTC')

      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Repository Key')).toBeInTheDocument()
      })
      setInputValue(screen.getByLabelText(/^Passphrase/i), 'scheduledpass')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await user.click(screen.getByRole('button', { name: /Create Repository/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Scheduled Cloud Repo',
            cloud_mirror_enabled: true,
            rclone_sync_policy: 'scheduled',
            rclone_sync_cron_expression: '*/30 * * * *',
            rclone_sync_timezone: 'UTC',
          }),
          null
        )
      })
    }, 90000)

    it('submits SSH repository cloud mirror fields without a cache path', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('create')

      await fillLocalLocation('SSH Cloud Repo', '/backups/ssh-cloud')
      await chooseRemoteRepository(user)

      const pathInput = screen.getByLabelText(/Repository Path/i)
      await user.clear(pathInput)
      setInputValue(pathInput, '/backups/ssh-cloud')

      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Mirror this repository to cloud storage')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('checkbox', { name: /Mirror this repository/i }))

      await user.click(screen.getByRole('combobox', { name: /Rclone Remote/i }))
      const remoteListbox = await screen.findByRole('listbox')
      await user.click(within(remoteListbox).getByText('prod-s3'))
      setInputValue(screen.getByLabelText(/Relative Remote Path/i), 'borg-ui/repositories/ssh')

      expect(screen.queryByText(/Local Cache Path/i)).not.toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Repository Key')).toBeInTheDocument()
      })
      setInputValue(screen.getByLabelText(/^Passphrase/i), 'sshcloudpass')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await user.click(screen.getByRole('button', { name: /Create Repository/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalled()
      })
      const [submittedPayload, submittedKeyFile] = onSubmit.mock.calls[0]
      expect(submittedPayload).not.toHaveProperty('rclone_cache_path')
      expect(submittedPayload).toEqual(
        expect.objectContaining({
          name: 'SSH Cloud Repo',
          path: '/backups/ssh-cloud',
          storage_backend: 'ssh',
          connection_id: 1,
          cloud_mirror_enabled: true,
          rclone_remote_id: 10,
          rclone_remote_path: 'borg-ui/repositories/ssh',
          rclone_remote_path_verified: false,
          rclone_sync_policy: 'after_success',
        })
      )
      expect(submittedKeyFile).toBeNull()
    }, 90000)

    it('submits managed-agent repository cloud mirror fields without a cache path', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('create')

      await waitForLocationStep()
      setInputValue(screen.getByLabelText(/Repository Name/i), 'Agent Cloud Repo')
      setInputValue(screen.getByLabelText(/Repository Path/i), '/srv/borg/agent-cloud-repo')
      await chooseDestination(user, /Managed Agent/i)
      await user.click(screen.getByRole('combobox', { name: /Managed Agent/i }))
      const agentListbox = await screen.findByRole('listbox')
      await user.click(within(agentListbox).getByText('workstation.local'))

      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Mirror this repository to cloud storage')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('checkbox', { name: /Mirror this repository/i }))
      expect(
        screen.getByText(/Selected managed agent syncs its repository path to the rclone remote/i)
      ).toBeInTheDocument()
      await user.click(screen.getByRole('combobox', { name: /Rclone Remote/i }))
      const remoteListbox = await screen.findByRole('listbox')
      await user.click(within(remoteListbox).getByText('prod-s3'))
      setInputValue(screen.getByLabelText(/Relative Remote Path/i), 'borg-ui/repositories/agent')

      expect(screen.queryByText(/Local Cache Path/i)).not.toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Repository Key')).toBeInTheDocument()
      })
      setInputValue(screen.getByLabelText(/^Passphrase/i), 'agentcloudpass')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await user.click(screen.getByRole('button', { name: /Create Repository/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalled()
      })
      const [submittedPayload, submittedKeyFile] = onSubmit.mock.calls[0]
      expect(submittedPayload).not.toHaveProperty('rclone_cache_path')
      expect(submittedPayload).toEqual(
        expect.objectContaining({
          name: 'Agent Cloud Repo',
          path: '/srv/borg/agent-cloud-repo',
          executor_type: 'agent',
          execution_target: 'agent',
          storage_backend: 'agent_local',
          agent_machine_id: 101,
          cloud_mirror_enabled: true,
          rclone_remote_id: 10,
          rclone_remote_path: 'borg-ui/repositories/agent',
          rclone_remote_path_verified: false,
          rclone_sync_policy: 'after_success',
        })
      )
      expect(submittedKeyFile).toBeNull()
    }, 90000)

    it('submits browsed cloud mirror paths as verified', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('create')
      ;(rcloneAPI.browseRemote as Mock)
        .mockResolvedValueOnce({
          data: {
            remote_id: 10,
            path: '',
            entries: [{ name: 'repositories', path: 'borg-ui/repositories', is_dir: true }],
          },
        })
        .mockResolvedValueOnce({
          data: {
            remote_id: 10,
            path: 'borg-ui/repositories',
            entries: [],
          },
        })

      await fillLocalLocation('Browsed Cloud Repo', '/backups/browsed-cloud-repo')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Mirror this repository to cloud storage')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('checkbox', { name: /Mirror this repository/i }))

      await user.click(screen.getByRole('combobox', { name: /Rclone Remote/i }))
      const remoteListbox = await screen.findByRole('listbox')
      await user.click(within(remoteListbox).getByText('prod-s3'))
      await user.click(screen.getByRole('button', { name: /Browse rclone remote/i }))
      const fileExplorerDialog = await screen.findByTestId('file-explorer-dialog')
      expect(fileExplorerDialog).toHaveAttribute('data-connection-type', 'rclone')
      await user.click(
        within(fileExplorerDialog).getByRole('button', {
          name: /Select browsed path/i,
          hidden: true,
        })
      )

      expect(screen.getByLabelText(/Relative Remote Path/i)).toHaveValue('borg-ui/repositories')
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Next/i })).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Repository Key')).toBeInTheDocument()
      })
      setInputValue(screen.getByLabelText(/^Passphrase/i), 'cloudpass')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await user.click(screen.getByRole('button', { name: /Create Repository/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Browsed Cloud Repo',
            storage_backend: 'local',
            cloud_mirror_enabled: true,
            rclone_remote_id: 10,
            rclone_remote_path: 'borg-ui/repositories',
            rclone_remote_path_verified: true,
            path: '/backups/browsed-cloud-repo',
          }),
          null
        )
      })
    }, 90000)

    it('adds and selects a rclone remote from the cloud mirror step', async () => {
      const user = userEvent.setup()
      ;(rcloneAPI.listRemotes as Mock).mockResolvedValue({
        data: { remotes: [] },
      })

      renderWizard('create')

      await fillLocalLocation('Cloud Repo', '/backups/cloud-repo')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await user.click(screen.getByRole('checkbox', { name: /Mirror this repository/i }))
      await user.click(screen.getByRole('button', { name: /Add remote/i }))

      await waitFor(() => {
        expect(rcloneAPI.getProviders).toHaveBeenCalled()
      })
      await user.click(screen.getByRole('combobox', { name: /^Provider/i }))
      const providerListbox = await screen.findByRole('listbox')
      expect(
        within(providerListbox).getByRole('option', { name: /Amazon S3 \/ S3-compatible/i })
      ).toBeInTheDocument()
      await user.click(within(providerListbox).getByRole('option', { name: /Local filesystem/i }))

      setInputValue(screen.getByLabelText(/Remote name/i), 'local-test')
      expect(screen.getByRole('combobox', { name: /^Provider/i })).toHaveTextContent(
        'Local filesystem'
      )
      setInputValue(screen.getByLabelText(/Config JSON/i), '{"type":"local"}')
      await user.click(screen.getByRole('button', { name: /Create remote/i }))

      await waitFor(() => {
        expect(rcloneAPI.createRemote).toHaveBeenCalledWith({
          name: 'local-test',
          provider: 'local',
          config_source: 'managed',
          redacted_config: { type: 'local' },
        })
      })
      await waitFor(() => {
        expect(screen.getByText('local-test')).toBeInTheDocument()
      })
    }, 90000)

    it('requires confirmed rclone availability before continuing enabled cloud mirror setup', async () => {
      const user = userEvent.setup()
      ;(rcloneAPI.getStatus as Mock).mockResolvedValue({
        data: { version: null, error: null },
      })

      renderWizard('create')

      await fillLocalLocation('Cloud Repo', '/backups/cloud-repo')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await user.click(screen.getByRole('checkbox', { name: /Mirror this repository/i }))

      expect(screen.getByRole('button', { name: /Next/i })).toBeDisabled()
    }, 90000)

    it('enables repository path browsing after selecting a managed agent', async () => {
      const user = userEvent.setup()
      renderWizard('create')

      await waitForLocationStep()
      setInputValue(screen.getByLabelText(/Repository Name/i), 'Agent Browse Repo')
      setInputValue(screen.getByLabelText(/Repository Path/i), '/srv/borg')

      await chooseDestination(user, /Managed Agent/i)
      await user.click(screen.getByRole('combobox', { name: /Managed Agent/i }))
      const agentListbox = await screen.findByRole('listbox')
      await user.click(within(agentListbox).getByText('workstation.local'))

      const browseButton = screen.getByTitle('Browse filesystem')
      expect(browseButton).not.toBeDisabled()
      await user.click(browseButton)

      expect(screen.getByTestId('file-explorer-dialog')).toHaveAttribute(
        'data-connection-type',
        'agent'
      )
      expect(screen.getByTestId('file-explorer-dialog')).toHaveAttribute('data-agent-id', '101')
      expect(screen.getByTestId('file-explorer-dialog')).toHaveAttribute(
        'data-agent-default-path',
        '/home/workstation'
      )

      await user.click(
        within(screen.getByTestId('file-explorer-dialog')).getByRole('button', {
          name: /select browsed path/i,
          hidden: true,
        })
      )
      expect(screen.getByLabelText(/Repository Path/i)).toHaveValue('/selected/from-browser')
    }, 90000)

    it('clears SSH repository target when managed-agent execution is selected', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('create')

      await fillLocalLocation('Agent SSH Repo', '/backups/pi')
      await chooseRemoteRepository(user)
      const pathInput = screen.getByLabelText(/Repository Path/i)
      await user.clear(pathInput)
      setInputValue(pathInput, '/backups/pi')

      await chooseDestination(user, /Managed Agent/i)
      await user.click(screen.getByRole('combobox', { name: /Managed Agent/i }))
      const agentListbox = await screen.findByRole('listbox')
      await user.click(within(agentListbox).getByText('workstation.local'))

      await user.click(screen.getByRole('combobox', { name: /Where should backups be stored/i }))
      const destinationListbox = await screen.findByRole('listbox')
      expect(
        within(destinationListbox).getByRole('option', { name: /Remote Client/i })
      ).not.toHaveAttribute('aria-disabled', 'true')
      await user.keyboard('{Escape}')

      expect(screen.queryByText('Select SSH Connection')).not.toBeInTheDocument()
      expect(
        screen.getByText(/Backups will be stored on the selected agent's filesystem/i)
      ).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Mirror this repository to cloud storage')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Repository Key')).toBeInTheDocument()
      })
      setInputValue(screen.getByLabelText(/^Passphrase/i), 'agentpass')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await user.click(screen.getByRole('button', { name: /Create Repository/i }))

      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Agent SSH Repo',
          path: '/backups/pi',
          executor_type: 'agent',
          execution_target: 'agent',
          storage_backend: 'agent_local',
          agent_machine_id: 101,
          connection_id: null,
          source_connection_id: null,
          source_directories: [],
          source_locations: [],
        }),
        null
      )
    }, 90000)
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
        expect(screen.getByText('Mirror this repository to cloud storage')).toBeInTheDocument()
      })
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
        expect(screen.getByText('Mirror this repository to cloud storage')).toBeInTheDocument()
      })
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
      await user.click(screen.getByRole('checkbox', { name: /Read-only storage access/i }))

      setInputValue(screen.getByLabelText(/Repository Name/i), 'Read Only Repo')
      setInputValue(screen.getByLabelText(/Repository Path/i), '/backup/readonly')
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Mirror this repository to cloud storage')).toBeInTheDocument()
      })
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

    it('populates existing direct Borg 2 rclone repositories without showing Cloud Mirror', async () => {
      renderWizard('edit', {
        id: 8,
        name: 'Direct Cloud Repo',
        path: 'rclone://prod-s3/borg-ui/direct',
        mode: 'full',
        repository_type: 'rclone',
        storage_backend: 'rclone_direct',
        borg_version: 2,
        encryption: 'repokey-aes-ocb',
        compression: 'lz4',
        rclone_storage: null,
      })

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('Direct Cloud Repo')
      })

      expect(screen.getByLabelText(/Direct rclone repository URL/i)).toHaveValue(
        'rclone://prod-s3/borg-ui/direct'
      )
      expect(
        screen.getByRole('checkbox', { name: /Use direct Borg 2 rclone repository/i })
      ).toBeChecked()
      expect(screen.queryByText('Cloud Mirror')).not.toBeInTheDocument()
    })

    it('submits cached rclone repository edits without primary storage conversion fields', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('edit', {
        id: 9,
        name: 'Cached Cloud Repo',
        path: '/cache/repositories/9',
        mode: 'full',
        repository_type: 'rclone',
        storage_backend: 'rclone',
        execution_target: 'local',
        executor_type: 'server',
        borg_version: 1,
        encryption: 'none',
        compression: 'lz4',
        connection_id: null,
        rclone_storage: {
          repository_id: 9,
          backend: 'rclone',
          rclone_remote_id: 10,
          rclone_remote_name: 'prod-s3',
          rclone_remote_path: 'borg-ui/repositories/app',
          cache_path: '/cache/repositories/9',
          sync_policy: 'manual',
          sync_status: 'current',
          extra_flags: ['--fast-list'],
        },
      })

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('Cached Cloud Repo')
      })

      const reviewStep = screen.getByText('Review').closest('div')
      expect(reviewStep).not.toBeNull()
      fireEvent.click(reviewStep!)

      await user.click(screen.getByRole('button', { name: /Save Changes/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalled()
      })
      const [submittedPayload] = onSubmit.mock.calls[0]
      expect(submittedPayload).toEqual(
        expect.objectContaining({
          name: 'Cached Cloud Repo',
          path: '/cache/repositories/9',
          storage_backend: 'rclone',
          rclone_remote_id: 10,
          rclone_remote_path: 'borg-ui/repositories/app',
          rclone_sync_policy: 'manual',
          rclone_extra_flags: ['--fast-list'],
        })
      )
      expect(submittedPayload).not.toHaveProperty('connection_id')
      expect(submittedPayload).not.toHaveProperty('execution_target')
      expect(submittedPayload).not.toHaveProperty('executor_type')
      expect(submittedPayload).not.toHaveProperty('agent_machine_id')
    })

    it('hydrates upload speed limits when editing a repository', async () => {
      renderWizard('edit', {
        id: 11,
        name: 'Throttled Repo',
        path: '/backups/throttled',
        mode: 'full',
        repository_type: 'local',
        storage_backend: 'local',
        execution_target: 'local',
        executor_type: 'server',
        borg_version: 1,
        encryption: 'none',
        compression: 'lz4',
        connection_id: null,
        rclone_storage: null,
        upload_ratelimit_kib: 1536,
      })

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('Throttled Repo')
      })

      const advancedStep = screen.getByText('Advanced').closest('div')
      expect(advancedStep).not.toBeNull()
      fireEvent.click(advancedStep!)

      await waitFor(() => {
        expect(screen.getByLabelText(/Upload speed limit/i)).toHaveValue('1.5')
      })
    })

    it('submits null when clearing an edited upload speed limit', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('edit', {
        id: 12,
        name: 'Clear Limit Repo',
        path: '/backups/clear-limit',
        mode: 'full',
        repository_type: 'local',
        storage_backend: 'local',
        execution_target: 'local',
        executor_type: 'server',
        borg_version: 1,
        encryption: 'none',
        compression: 'lz4',
        connection_id: null,
        rclone_storage: null,
        upload_ratelimit_kib: 2048,
      })

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('Clear Limit Repo')
      })

      const advancedStep = screen.getByText('Advanced').closest('div')
      expect(advancedStep).not.toBeNull()
      fireEvent.click(advancedStep!)
      await waitFor(() => {
        expect(screen.getByLabelText(/Upload speed limit/i)).toBeInTheDocument()
      })
      await user.clear(screen.getByLabelText(/Upload speed limit/i))

      const reviewStep = screen.getByText('Review').closest('div')
      expect(reviewStep).not.toBeNull()
      fireEvent.click(reviewStep!)
      await user.click(screen.getByRole('button', { name: /Save Changes/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalled()
      })
      const [submittedPayload] = onSubmit.mock.calls[0]
      expect(submittedPayload).toEqual(
        expect.objectContaining({
          upload_ratelimit_kib: null,
        })
      )
    })

    it('preserves tiny positive upload speed limits when submitting unchanged edits', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('edit', {
        id: 13,
        name: 'Tiny Limit Repo',
        path: '/backups/tiny-limit',
        mode: 'full',
        repository_type: 'local',
        storage_backend: 'local',
        execution_target: 'local',
        executor_type: 'server',
        borg_version: 1,
        encryption: 'none',
        compression: 'lz4',
        connection_id: null,
        rclone_storage: null,
        upload_ratelimit_kib: 1,
      })

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('Tiny Limit Repo')
      })

      const advancedStep = screen.getByText('Advanced').closest('div')
      expect(advancedStep).not.toBeNull()
      fireEvent.click(advancedStep!)
      await waitFor(() => {
        expect(screen.getByLabelText(/Upload speed limit/i)).toHaveValue('0.001')
      })

      const reviewStep = screen.getByText('Review').closest('div')
      expect(reviewStep).not.toBeNull()
      fireEvent.click(reviewStep!)
      await user.click(screen.getByRole('button', { name: /Save Changes/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalled()
      })
      const [submittedPayload] = onSubmit.mock.calls[0]
      expect(submittedPayload).toEqual(
        expect.objectContaining({
          upload_ratelimit_kib: 1,
        })
      )
    })

    it('allows edit workflow without re-entering the passphrase', async () => {
      const user = userEvent.setup()
      renderWizard('edit', legacyRepository)

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('Legacy Repo')
      })

      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(() => {
        expect(screen.getByText('Mirror this repository to cloud storage')).toBeInTheDocument()
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
      renderWizard('edit', legacyRepository)

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('Legacy Repo')
      })

      const reviewStep = screen.getByText('Review').closest('div')
      expect(reviewStep).not.toBeNull()
      fireEvent.click(reviewStep!)

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Save Changes/i })).toBeInTheDocument()
      })
    })

    it('submits local repository edits without disabled rclone defaults', async () => {
      const user = userEvent.setup()
      const { onSubmit } = renderWizard('edit', {
        id: 10,
        name: 'Local Repo',
        path: '/backups/local',
        mode: 'full',
        repository_type: 'local',
        storage_backend: 'local',
        execution_target: 'local',
        executor_type: 'server',
        borg_version: 1,
        encryption: 'none',
        compression: 'lz4',
        connection_id: null,
        rclone_storage: null,
      })

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('Local Repo')
      })

      const reviewStep = screen.getByText('Review').closest('div')
      expect(reviewStep).not.toBeNull()
      fireEvent.click(reviewStep!)

      await user.click(screen.getByRole('button', { name: /Save Changes/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalled()
      })
      const [submittedPayload] = onSubmit.mock.calls[0]
      expect(submittedPayload).toEqual(
        expect.objectContaining({
          name: 'Local Repo',
          path: '/backups/local',
          storage_backend: 'local',
        })
      )
      expect(submittedPayload).not.toHaveProperty('cloud_mirror_enabled')
      expect(submittedPayload).not.toHaveProperty('rclone_remote_id')
      expect(submittedPayload).not.toHaveProperty('rclone_remote_path')
      expect(submittedPayload).not.toHaveProperty('rclone_remote_path_verified')
      expect(submittedPayload).not.toHaveProperty('rclone_sync_policy')
      expect(submittedPayload).not.toHaveProperty('rclone_sync_cron_expression')
      expect(submittedPayload).not.toHaveProperty('rclone_sync_timezone')
      expect(submittedPayload).not.toHaveProperty('rclone_extra_flags')
    })
  })

  describe('SSH and loading behavior', () => {
    it('handles API errors when SSH connections cannot load', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      ;(sshKeysAPI.getSSHConnections as Mock).mockRejectedValue(new Error('Network Error'))
      const user = userEvent.setup()
      renderWizard('create')

      await waitForLocationStep()
      await chooseDestination(user, /Remote Client/i)

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
