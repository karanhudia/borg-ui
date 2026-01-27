import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, Mock, vi } from 'vitest'
import RepositoryWizard from '../RepositoryWizard'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { sshKeysAPI } from '../../services/api'

// Mock the API
vi.mock('../../services/api', () => ({
  sshKeysAPI: {
    getSSHConnections: vi.fn(),
  },
}))

// Mock Matomo hook
vi.mock('../../hooks/useMatomo', () => ({
  useMatomo: () => ({
    track: vi.fn(),
    trackRepository: vi.fn(),
    EventCategory: { REPOSITORY: 'repository' },
    EventAction: { CREATE: 'create', EDIT: 'edit', UPLOAD: 'upload' },
  }),
}))

// Mock child components
vi.mock('../CompressionSettings', () => ({
  default: ({ compression }: { compression: string }) => (
    <div data-testid="compression-settings">Compression: {compression}</div>
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

// Mock AdvancedRepositoryOptions to include Custom Borg Flags input
vi.mock('../AdvancedRepositoryOptions', () => ({
  default: ({
    customFlags,
    onCustomFlagsChange,
  }: {
    customFlags: string
    onCustomFlagsChange: (value: string) => void
  }) => (
    <div data-testid="advanced-options">
      <label htmlFor="custom-borg-flags">Custom Borg Flags</label>
      <input
        id="custom-borg-flags"
        value={customFlags}
        onChange={(e) => onCustomFlagsChange(e.target.value)}
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

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

const renderWizard = (
  mode: 'create' | 'import' | 'edit' = 'create',
  repository?: object,
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

describe('RepositoryWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(sshKeysAPI.getSSHConnections as Mock).mockResolvedValue({
      data: { connections: mockSshConnections },
    })
  })

  // ============================================================
  // CREATE MODE - Complete Step-by-Step Tests
  // ============================================================
  describe('Create Mode', () => {
    describe('Step 1: Repository Location', () => {
      it('shows correct dialog title', async () => {
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByText('Create Repository')).toBeInTheDocument()
        })
      })

      it('shows all 5 steps in stepper', async () => {
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByText('Repository Location')).toBeInTheDocument()
        })
        expect(screen.getByText('Data Source')).toBeInTheDocument()
        expect(screen.getByText('Security')).toBeInTheDocument()
        expect(screen.getByText('Backup Configuration')).toBeInTheDocument()
        expect(screen.getByText('Review')).toBeInTheDocument()
      })

      it('renders Repository Name input', async () => {
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })
      })

      it('renders Repository Path input', async () => {
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Path/i)).toBeInTheDocument()
        })
      })

      it('shows location cards (Borg UI Server and Remote Client)', async () => {
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByText('Borg UI Server')).toBeInTheDocument()
        })
        expect(screen.getByText('Remote Client')).toBeInTheDocument()
      })

      it('does NOT show Repository Mode selector (only in import mode)', async () => {
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        expect(screen.queryByLabelText(/Repository Mode/i)).not.toBeInTheDocument()
        expect(screen.queryByText('Full Repository')).not.toBeInTheDocument()
        expect(screen.queryByText('Observability Only')).not.toBeInTheDocument()
      })

      it('Next button is disabled when name is empty', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Path/i)).toBeInTheDocument()
        })

        await user.type(screen.getByLabelText(/Repository Path/i), '/backups/test')

        expect(screen.getByRole('button', { name: /Next/i })).toBeDisabled()
      })

      it('Next button is disabled when path is empty', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await user.type(screen.getByLabelText(/Repository Name/i), 'Test Repo')

        expect(screen.getByRole('button', { name: /Next/i })).toBeDisabled()
      })

      it('Next button is enabled when name and path are filled', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await user.type(screen.getByLabelText(/Repository Name/i), 'Test Repo')
        await user.type(screen.getByLabelText(/Repository Path/i), '/backups/test')

        expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled()
      })

      it('clicking Remote Client changes path placeholder', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByText('Remote Client')).toBeInTheDocument()
        })

        // Initially, path placeholder should be for local
        expect(screen.getByPlaceholderText(/\/backups\/my-repo/i)).toBeInTheDocument()

        const remoteCard = screen.getByText('Remote Client').closest('button')
        await user.click(remoteCard!)

        // After clicking Remote Client, placeholder should change
        await waitFor(() => {
          expect(screen.getByPlaceholderText(/\/path\/on\/remote\/server/i)).toBeInTheDocument()
        })
      })

      it('Next button is disabled when Remote Client selected but no SSH connection chosen', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByText('Remote Client')).toBeInTheDocument()
        })

        await user.type(screen.getByLabelText(/Repository Name/i), 'Test Repo')
        await user.type(screen.getByLabelText(/Repository Path/i), '/backups/test')

        const remoteCard = screen.getByText('Remote Client').closest('button')
        await user.click(remoteCard!)

        expect(screen.getByRole('button', { name: /Next/i })).toBeDisabled()
      })

      it('shows warning when no SSH connections available', async () => {
        ;(sshKeysAPI.getSSHConnections as Mock).mockResolvedValue({
          data: { connections: [] },
        })

        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByText('Remote Client')).toBeInTheDocument()
        })

        const remoteCard = screen.getByText('Remote Client').closest('button')
        await user.click(remoteCard!)

        await waitFor(() => {
          expect(screen.getByText(/No SSH connections configured/i)).toBeInTheDocument()
        })
      })
    })

    describe('Step 2: Data Source', () => {
      const goToStep2 = async (user: ReturnType<typeof userEvent.setup>) => {
        await user.type(screen.getByLabelText(/Repository Name/i), 'Test Repo')
        await user.type(screen.getByLabelText(/Repository Path/i), '/backups/test')
        await user.click(screen.getByRole('button', { name: /Next/i }))

        await waitFor(() => {
          expect(screen.getByText(/Where is the data you want to back up/i)).toBeInTheDocument()
        })
      }

      it('shows data source question', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep2(user)

        expect(screen.getByText(/Where is the data you want to back up/i)).toBeInTheDocument()
      })

      it('shows Borg UI Server and Remote Machine cards', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep2(user)

        expect(screen.getByText('Remote Machine')).toBeInTheDocument()
      })

      it('shows Source Directories section', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep2(user)

        expect(screen.getByText('Source Directories')).toBeInTheDocument()
      })

      it('shows required asterisk for source directories', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep2(user)

        expect(screen.getByText(/at least one required/i)).toBeInTheDocument()
      })

      it('shows warning when no source directories added', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep2(user)

        expect(screen.getByText(/At least one source directory is required/i)).toBeInTheDocument()
      })

      it('Next button is disabled without source directories', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep2(user)

        expect(screen.getByRole('button', { name: /Next/i })).toBeDisabled()
      })

      it('can add source directory and enable Next button', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep2(user)

        const dirInput = screen.getByPlaceholderText('/home/user/documents')
        await user.type(dirInput, '/home/user/data')
        await user.click(screen.getByRole('button', { name: /Add/i }))

        expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled()
      })

      it('Back button returns to Step 1', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep2(user)

        // Find the Back button in the dialog actions (exact match)
        const backButton = screen.getByRole('button', { name: 'Back' })
        await user.click(backButton)

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('Test Repo')
        })
      })
    })

    describe('Step 3: Security', () => {
      const goToStep3 = async (user: ReturnType<typeof userEvent.setup>) => {
        // Step 1: Fill in name and path
        await user.type(screen.getByLabelText(/Repository Name/i), 'Test Repo')
        await user.type(screen.getByLabelText(/Repository Path/i), '/backups/test')
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 2: Wait for Data Source step and add source directory
        await waitFor(
          () => {
            expect(screen.getByText('Source Directories')).toBeInTheDocument()
          },
          { timeout: 5000 }
        )

        const dirInput = screen.getByPlaceholderText('/home/user/documents')
        await user.type(dirInput, '/home/user')
        await user.click(screen.getByRole('button', { name: /Add/i }))

        await waitFor(() => {
          expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled()
        })
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 3: Wait for Security step - look for Remote Path which is unique
        await waitFor(
          () => {
            expect(screen.getByLabelText(/Remote Path/i)).toBeInTheDocument()
          },
          { timeout: 5000 }
        )
      }

      it('shows Encryption dropdown', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep3(user)

        // Look for the MUI Select element with "Repokey (Recommended)" as the default value
        expect(screen.getByText('Repokey (Recommended)')).toBeInTheDocument()
      })

      it('shows Passphrase input', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep3(user)

        // The passphrase input has label text "Passphrase"
        expect(screen.getByLabelText(/^Passphrase/i)).toBeInTheDocument()
      })

      it('shows Remote Borg Path input', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep3(user)

        expect(screen.getByLabelText(/Remote Path/i)).toBeInTheDocument()
      })

      it('Next button is disabled without passphrase when encryption is enabled', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep3(user)

        expect(screen.getByRole('button', { name: /Next/i })).toBeDisabled()
      })

      it('Next button is enabled after entering passphrase', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep3(user)

        // Find and fill the passphrase input
        const passphraseInput = screen.getByLabelText(/^Passphrase/i)
        await user.type(passphraseInput, 'mysecretpass')

        expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled()
      })
    })

    describe('Step 4: Backup Configuration', () => {
      const goToStep4 = async (user: ReturnType<typeof userEvent.setup>) => {
        // Step 1
        await user.type(screen.getByLabelText(/Repository Name/i), 'Test Repo')
        await user.type(screen.getByLabelText(/Repository Path/i), '/backups/test')
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 2
        await waitFor(
          () => {
            expect(screen.getByText('Source Directories')).toBeInTheDocument()
          },
          { timeout: 5000 }
        )

        const dirInput = screen.getByPlaceholderText('/home/user/documents')
        await user.type(dirInput, '/home/user')
        await user.click(screen.getByRole('button', { name: /Add/i }))

        await waitFor(() => {
          expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled()
        })
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 3
        await waitFor(
          () => {
            expect(screen.getByLabelText(/Remote Path/i)).toBeInTheDocument()
          },
          { timeout: 5000 }
        )

        await user.type(screen.getByLabelText(/^Passphrase/i), 'testpass123')
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 4
        await waitFor(
          () => {
            expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
          },
          { timeout: 5000 }
        )
      }

      it('shows compression settings', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep4(user)

        expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
      })

      it('shows exclude patterns section', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep4(user)

        expect(screen.getByTestId('exclude-patterns')).toBeInTheDocument()
      })

      it('shows Custom Borg Flags input', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep4(user)

        expect(screen.getByLabelText(/Custom Borg Flags/i)).toBeInTheDocument()
      })

      it('Next button is always enabled on this step', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep4(user)

        expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled()
      })
    })

    describe('Step 5: Review', () => {
      const goToStep5 = async (user: ReturnType<typeof userEvent.setup>) => {
        // Step 1
        await user.type(screen.getByLabelText(/Repository Name/i), 'Test Repo')
        await user.type(screen.getByLabelText(/Repository Path/i), '/backups/test')
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 2
        await waitFor(
          () => {
            expect(screen.getByText('Source Directories')).toBeInTheDocument()
          },
          { timeout: 5000 }
        )

        const dirInput = screen.getByPlaceholderText('/home/user/documents')
        await user.type(dirInput, '/home/user')
        await user.click(screen.getByRole('button', { name: /Add/i }))

        await waitFor(() => {
          expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled()
        })
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 3
        await waitFor(
          () => {
            expect(screen.getByLabelText(/Remote Path/i)).toBeInTheDocument()
          },
          { timeout: 5000 }
        )

        await user.type(screen.getByLabelText(/^Passphrase/i), 'testpass123')
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 4
        await waitFor(
          () => {
            expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
          },
          { timeout: 5000 }
        )

        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 5
        await waitFor(
          () => {
            expect(screen.getByTestId('command-preview')).toBeInTheDocument()
          },
          { timeout: 5000 }
        )
      }

      it('shows command preview', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep5(user)

        expect(screen.getByTestId('command-preview')).toBeInTheDocument()
      })

      it('shows Create Repository button (not Next)', async () => {
        const user = userEvent.setup()
        renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep5(user)

        expect(screen.getByRole('button', { name: /Create Repository/i })).toBeInTheDocument()
        expect(screen.queryByRole('button', { name: /^Next$/i })).not.toBeInTheDocument()
      })

      it('submits correct data when Create Repository is clicked', async () => {
        const user = userEvent.setup()
        const { onSubmit } = renderWizard('create')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep5(user)

        await user.click(screen.getByRole('button', { name: /Create Repository/i }))

        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Test Repo',
            path: '/backups/test',
            mode: 'full',
            repository_type: 'local',
            encryption: 'repokey',
            passphrase: 'testpass123',
            source_directories: ['/home/user'],
            compression: 'lz4',
          })
        )
      })
    })
  })

  // ============================================================
  // IMPORT MODE (FULL) - Complete Step-by-Step Tests
  // ============================================================
  describe('Import Mode (Full Repository)', () => {
    describe('Step 1: Repository Location', () => {
      it('shows correct dialog title', async () => {
        renderWizard('import')

        await waitFor(() => {
          expect(screen.getByText('Import Repository')).toBeInTheDocument()
        })
      })

      it('shows Repository Mode selector (Full/Observe)', async () => {
        renderWizard('import')

        await waitFor(() => {
          // MUI Select shows the selected value "Full Repository" and the label
          expect(screen.getByText('Full Repository')).toBeInTheDocument()
        })
      })

      it('shows Full Repository option text', async () => {
        renderWizard('import')

        await waitFor(() => {
          expect(screen.getByText('Full Repository')).toBeInTheDocument()
        })
      })

      it('Full Repository is selected by default', async () => {
        renderWizard('import')

        await waitFor(() => {
          expect(screen.getByText('Full Repository')).toBeInTheDocument()
        })

        // The "Full Repository" text should be visible as the selected option
        expect(screen.getByText(/Create backups and browse archives/i)).toBeInTheDocument()
      })

      it('does NOT show bypass lock checkbox when Full mode is selected', async () => {
        renderWizard('import')

        await waitFor(() => {
          expect(screen.getByText('Full Repository')).toBeInTheDocument()
        })

        expect(screen.queryByText(/Read-only storage access/i)).not.toBeInTheDocument()
      })
    })

    describe('Step 2: Data Source', () => {
      const goToStep2Import = async (user: ReturnType<typeof userEvent.setup>) => {
        await user.type(screen.getByLabelText(/Repository Name/i), 'Imported Repo')
        await user.type(screen.getByLabelText(/Repository Path/i), '/existing/repo')
        await user.click(screen.getByRole('button', { name: /Next/i }))

        await waitFor(() => {
          expect(screen.getByText('Source Directories')).toBeInTheDocument()
        })
      }

      it('shows Source Directories as required', async () => {
        const user = userEvent.setup()
        renderWizard('import')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep2Import(user)

        expect(screen.getByText(/at least one required/i)).toBeInTheDocument()
      })

      it('Next button is disabled without source directories', async () => {
        const user = userEvent.setup()
        renderWizard('import')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await goToStep2Import(user)

        expect(screen.getByRole('button', { name: /Next/i })).toBeDisabled()
      })
    })

    describe('Full Workflow Submission', () => {
      it('submits with mode=full and correct data', async () => {
        const user = userEvent.setup()
        const { onSubmit } = renderWizard('import')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        // Step 1
        await user.type(screen.getByLabelText(/Repository Name/i), 'Imported Full Repo')
        await user.type(screen.getByLabelText(/Repository Path/i), '/existing/backup')
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 2
        await waitFor(() => {
          expect(screen.getByText('Source Directories')).toBeInTheDocument()
        })
        const dirInput = screen.getByPlaceholderText('/home/user/documents')
        await user.type(dirInput, '/data/important')
        await user.click(screen.getByRole('button', { name: /Add/i }))
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 3
        await waitFor(() => {
          expect(screen.getByLabelText(/Passphrase/i)).toBeInTheDocument()
        })
        await user.type(screen.getByLabelText(/Passphrase/i), 'importpass')
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 4
        await waitFor(() => {
          expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
        })
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 5
        await waitFor(() => {
          expect(screen.getByRole('button', { name: /Import Repository/i })).toBeInTheDocument()
        })
        await user.click(screen.getByRole('button', { name: /Import Repository/i }))

        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Imported Full Repo',
            path: '/existing/backup',
            mode: 'full',
            passphrase: 'importpass',
            source_directories: ['/data/important'],
            bypass_lock: false,
          })
        )
      })
    })
  })

  // ============================================================
  // IMPORT MODE (OBSERVE) - Complete Step-by-Step Tests
  // ============================================================
  describe('Import Mode (Observability Only)', () => {
    const selectObserveMode = async (user: ReturnType<typeof userEvent.setup>) => {
      // MUI Select renders a hidden native select and a visible button
      // The button has the displayed value and opens the dropdown
      // We need to find the MUI Select's button element by locating the parent FormControl
      // and clicking the select within it

      // Wait for the component to render
      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
      })

      // Find all buttons that contain "Full Repository" and click the one in the select
      const selectButtons = screen.getAllByText('Full Repository')
      // The button element (not Typography) will have the click handler
      const selectButton =
        selectButtons.find(
          (el) => el.closest('[role="combobox"]') || el.closest('.MuiSelect-select')
        ) || selectButtons[0]

      await user.click(selectButton)

      // Wait for the listbox to appear
      const listbox = await screen.findByRole('listbox', {}, { timeout: 3000 })

      // Find and click the Observability Only option
      const observeOption = within(listbox).getByText('Observability Only')
      await user.click(observeOption)
    }

    describe('Step 1: Repository Location', () => {
      it('can select Observability Only mode', async () => {
        const user = userEvent.setup()
        renderWizard('import')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await selectObserveMode(user)

        // Should show the observe mode alert
        await waitFor(
          () => {
            expect(
              screen.getByText(/Observability-only repositories can browse and restore/i)
            ).toBeInTheDocument()
          },
          { timeout: 5000 }
        )
      })

      it('shows bypass lock checkbox when Observe mode is selected', async () => {
        const user = userEvent.setup()
        renderWizard('import')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await selectObserveMode(user)

        await waitFor(
          () => {
            expect(screen.getByText(/Read-only storage access/i)).toBeInTheDocument()
          },
          { timeout: 5000 }
        )
      })

      it('bypass lock checkbox is unchecked by default', async () => {
        const user = userEvent.setup()
        renderWizard('import')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await selectObserveMode(user)

        await waitFor(
          () => {
            expect(screen.getByText(/Read-only storage access/i)).toBeInTheDocument()
          },
          { timeout: 5000 }
        )

        const checkbox = screen.getByRole('checkbox')
        expect(checkbox).not.toBeChecked()
      })

      it('can check bypass lock checkbox', async () => {
        const user = userEvent.setup()
        renderWizard('import')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await selectObserveMode(user)

        await waitFor(
          () => {
            expect(screen.getByText(/Read-only storage access/i)).toBeInTheDocument()
          },
          { timeout: 5000 }
        )

        await user.click(screen.getByRole('checkbox'))

        expect(screen.getByRole('checkbox')).toBeChecked()
      })
    })

    describe('Step 2: Data Source', () => {
      const goToStep2Observe = async (user: ReturnType<typeof userEvent.setup>) => {
        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        await selectObserveMode(user)

        await waitFor(
          () => {
            expect(screen.getByText(/Read-only storage access/i)).toBeInTheDocument()
          },
          { timeout: 5000 }
        )

        await user.type(screen.getByLabelText(/Repository Name/i), 'Observe Repo')
        await user.type(screen.getByLabelText(/Repository Path/i), '/readonly/repo')
        await user.click(screen.getByRole('button', { name: /Next/i }))

        await waitFor(
          () => {
            expect(screen.getByText('Source Directories')).toBeInTheDocument()
          },
          { timeout: 5000 }
        )
      }

      it('shows Source Directories as optional', async () => {
        const user = userEvent.setup()
        renderWizard('import')

        await goToStep2Observe(user)

        expect(screen.getByText(/\(optional\)/i)).toBeInTheDocument()
      })

      it('does NOT show required warning', async () => {
        const user = userEvent.setup()
        renderWizard('import')

        await goToStep2Observe(user)

        expect(
          screen.queryByText(/At least one source directory is required/i)
        ).not.toBeInTheDocument()
      })

      it('Next button is ENABLED without source directories (optional)', async () => {
        const user = userEvent.setup()
        renderWizard('import')

        await goToStep2Observe(user)

        // This is the key difference - in observe mode, source dirs are optional
        expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled()
      })

      it('can still add source directories if desired', async () => {
        const user = userEvent.setup()
        renderWizard('import')

        await goToStep2Observe(user)

        const dirInput = screen.getByPlaceholderText('/home/user/documents')
        await user.type(dirInput, '/optional/dir')
        await user.click(screen.getByRole('button', { name: /Add/i }))

        // Should show the added directory
        expect(screen.getByText('/optional/dir')).toBeInTheDocument()
      })
    })

    describe('Full Workflow Submission (without source dirs)', () => {
      it('submits with mode=observe and bypass_lock=true', async () => {
        const user = userEvent.setup()
        const { onSubmit } = renderWizard('import')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        // Step 1 - Select observe mode and enable bypass lock
        await selectObserveMode(user)
        await waitFor(
          () => {
            expect(screen.getByRole('checkbox')).toBeInTheDocument()
          },
          { timeout: 5000 }
        )
        await user.click(screen.getByRole('checkbox'))

        await user.type(screen.getByLabelText(/Repository Name/i), 'Read Only Repo')
        await user.type(screen.getByLabelText(/Repository Path/i), '/backup/readonly')
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 2 - Skip adding source directories (they're optional)
        await waitFor(
          () => {
            expect(screen.getByText(/\(optional\)/i)).toBeInTheDocument()
          },
          { timeout: 5000 }
        )
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 3 - Security
        await waitFor(
          () => {
            expect(screen.getByLabelText(/Remote Path/i)).toBeInTheDocument()
          },
          { timeout: 5000 }
        )
        await user.type(screen.getByLabelText(/^Passphrase/i), 'observepass')
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 4 - Backup Configuration
        await waitFor(
          () => {
            expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
          },
          { timeout: 5000 }
        )
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 5 - Review and Submit
        await waitFor(
          () => {
            expect(screen.getByRole('button', { name: /Import Repository/i })).toBeInTheDocument()
          },
          { timeout: 5000 }
        )
        await user.click(screen.getByRole('button', { name: /Import Repository/i }))

        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Read Only Repo',
            path: '/backup/readonly',
            mode: 'observe',
            bypass_lock: true,
            source_directories: [],
          })
        )
      })

      it('submits with mode=observe and source directories when provided', async () => {
        const user = userEvent.setup()
        const { onSubmit } = renderWizard('import')

        await waitFor(() => {
          expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
        })

        // Step 1
        await selectObserveMode(user)
        await waitFor(
          () => {
            expect(screen.getByText(/Read-only storage access/i)).toBeInTheDocument()
          },
          { timeout: 5000 }
        )

        await user.type(screen.getByLabelText(/Repository Name/i), 'Observe With Dirs')
        await user.type(screen.getByLabelText(/Repository Path/i), '/backup/observe')
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 2 - Add optional source directory
        await waitFor(
          () => {
            expect(screen.getByText(/\(optional\)/i)).toBeInTheDocument()
          },
          { timeout: 5000 }
        )
        const dirInput = screen.getByPlaceholderText('/home/user/documents')
        await user.type(dirInput, '/optional/source')
        await user.click(screen.getByRole('button', { name: /Add/i }))
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 3
        await waitFor(
          () => {
            expect(screen.getByLabelText(/Remote Path/i)).toBeInTheDocument()
          },
          { timeout: 5000 }
        )
        await user.type(screen.getByLabelText(/^Passphrase/i), 'pass123')
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 4
        await waitFor(
          () => {
            expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
          },
          { timeout: 5000 }
        )
        await user.click(screen.getByRole('button', { name: /Next/i }))

        // Step 5
        await waitFor(
          () => {
            expect(screen.getByRole('button', { name: /Import Repository/i })).toBeInTheDocument()
          },
          { timeout: 5000 }
        )
        await user.click(screen.getByRole('button', { name: /Import Repository/i }))

        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Observe With Dirs',
            mode: 'observe',
            source_directories: ['/optional/source'],
            bypass_lock: false,
          })
        )
      })
    })
  })

  // ============================================================
  // EDIT MODE - Tests
  // ============================================================
  describe('Edit Mode', () => {
    it('shows correct dialog title', async () => {
      const existingRepo = {
        name: 'Existing Repo',
        path: '/backups/existing',
        mode: 'full',
        source_directories: ['/data'],
        repository_type: 'local',
      }
      renderWizard('edit', existingRepo)

      await waitFor(() => {
        expect(screen.getByText('Edit Repository')).toBeInTheDocument()
      })
    })

    it('populates form with existing data', async () => {
      const existingRepo = {
        name: 'My Backup Repo',
        path: '/backups/myrepo',
        mode: 'full',
        source_directories: ['/home/user'],
        repository_type: 'local',
      }
      renderWizard('edit', existingRepo)

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('My Backup Repo')
      })
      expect(screen.getByLabelText(/Repository Path/i)).toHaveValue('/backups/myrepo')
    })

    it('shows Save Changes button on final step', async () => {
      const user = userEvent.setup()
      const existingRepo = {
        name: 'Edit Repo',
        path: '/backups/edit',
        mode: 'full',
        source_directories: ['/data'],
        repository_type: 'local',
      }
      renderWizard('edit', existingRepo)

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('Edit Repo')
      })

      // Navigate through all steps
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(
        () => {
          expect(screen.getByText('Source Directories')).toBeInTheDocument()
        },
        { timeout: 5000 }
      )

      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(
        () => {
          // In edit mode, look for Remote Path (Security step)
          expect(screen.getByLabelText(/Remote Path/i)).toBeInTheDocument()
        },
        { timeout: 5000 }
      )

      // In edit mode, passphrase is not required
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(
        () => {
          expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
        },
        { timeout: 5000 }
      )

      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(
        () => {
          expect(screen.getByRole('button', { name: /Save Changes/i })).toBeInTheDocument()
        },
        { timeout: 5000 }
      )
    })

    it('passphrase is NOT required in edit mode', async () => {
      const user = userEvent.setup()
      const existingRepo = {
        name: 'Edit Repo',
        path: '/backups/edit',
        mode: 'full',
        source_directories: ['/data'],
        repository_type: 'local',
        encryption: 'repokey',
      }
      renderWizard('edit', existingRepo)

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('Edit Repo')
      })

      // Go to step 2
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(
        () => {
          expect(screen.getByText('Source Directories')).toBeInTheDocument()
        },
        { timeout: 5000 }
      )

      // Go to step 3 (Security)
      await user.click(screen.getByRole('button', { name: /Next/i }))
      await waitFor(
        () => {
          expect(screen.getByLabelText(/Remote Path/i)).toBeInTheDocument()
        },
        { timeout: 5000 }
      )

      // Next button should be enabled even without passphrase
      expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled()
    })

    it('parses SSH URL format correctly', async () => {
      const existingRepo = {
        name: 'SSH Repo',
        path: 'ssh://admin@backup.server.com:2222/data/backups',
        mode: 'full',
        source_directories: ['/important'],
        repository_type: 'ssh',
      }
      renderWizard('edit', existingRepo)

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toHaveValue('SSH Repo')
      })
      // Path should be extracted from SSH URL
      expect(screen.getByLabelText(/Repository Path/i)).toHaveValue('/data/backups')
    })
  })

  // ============================================================
  // SSH Connection Handling
  // ============================================================
  describe('SSH Connection Handling', () => {
    it('handles API error gracefully', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      ;(sshKeysAPI.getSSHConnections as Mock).mockRejectedValue(new Error('Network Error'))

      const user = userEvent.setup()
      renderWizard('create')

      await waitFor(() => {
        expect(screen.getByText('Remote Client')).toBeInTheDocument()
      })

      const remoteCard = screen.getByText('Remote Client').closest('button')
      await user.click(remoteCard!)

      await waitFor(() => {
        expect(screen.getByText(/No SSH connections configured/i)).toBeInTheDocument()
      })

      consoleSpy.mockRestore()
    })

    it('handles null connections response', async () => {
      ;(sshKeysAPI.getSSHConnections as Mock).mockResolvedValue({
        data: { connections: null },
      })

      const user = userEvent.setup()
      renderWizard('create')

      await waitFor(() => {
        expect(screen.getByText('Remote Client')).toBeInTheDocument()
      })

      const remoteCard = screen.getByText('Remote Client').closest('button')
      await user.click(remoteCard!)

      await waitFor(() => {
        expect(screen.getByText(/No SSH connections configured/i)).toBeInTheDocument()
      })
    })
  })

  // ============================================================
  // Navigation Tests
  // ============================================================
  describe('Navigation', () => {
    it('Cancel button calls onClose', async () => {
      const user = userEvent.setup()
      const { onClose } = renderWizard('create')

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Cancel/i })).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: /Cancel/i }))

      expect(onClose).toHaveBeenCalled()
    })

    it('Back button is disabled on first step', async () => {
      renderWizard('create')

      await waitFor(() => {
        expect(screen.getByLabelText(/Repository Name/i)).toBeInTheDocument()
      })

      // Use exact match to find the Back button in dialog actions
      expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled()
    })
  })
})
