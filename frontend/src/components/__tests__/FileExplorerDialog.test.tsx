import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/test-utils'
import FileExplorerDialog from '../FileExplorerDialog'
import api from '../../services/api'
import { sshKeysAPI } from '../../services/api'

// Mock the API
vi.mock('../../services/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
  sshKeysAPI: {
    getSSHConnections: vi.fn(),
  },
}))

describe('FileExplorerDialog', () => {
  const mockOnClose = vi.fn()
  const mockOnSelect = vi.fn()

  const mockDirectoryResponse = {
    data: {
      current_path: '/home/user',
      items: [
        {
          name: 'Documents',
          path: '/home/user/Documents',
          is_directory: true,
          is_borg_repo: false,
        },
        {
          name: 'file.txt',
          path: '/home/user/file.txt',
          is_directory: false,
          is_borg_repo: false,
          size: 1024,
        },
        {
          name: 'backup-repo',
          path: '/home/user/backup-repo',
          is_directory: true,
          is_borg_repo: true,
        },
      ],
      is_inside_local_mount: false,
    },
  }

  const mockEmptyDirectoryResponse = {
    data: {
      current_path: '/empty',
      items: [],
      is_inside_local_mount: false,
    },
  }

  const mockSSHConnectionsResponse = {
    data: {
      connections: [
        {
          id: 1,
          ssh_key_id: 1,
          host: 'remote.server.com',
          username: 'user',
          port: 22,
          status: 'connected',
          mount_point: 'Remote Server',
          default_path: '/home/user',
        },
      ],
    },
    status: 200,
    statusText: 'OK',
    headers: {},
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    config: {} as any,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.get).mockResolvedValue(mockDirectoryResponse)
    vi.mocked(sshKeysAPI.getSSHConnections).mockResolvedValue(mockSSHConnectionsResponse)
  })

  describe('Basic Rendering', () => {
    it('renders dialog when open', async () => {
      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('Select Directory')).toBeInTheDocument()
      })
    })

    it('does not render when closed', () => {
      renderWithProviders(
        <FileExplorerDialog open={false} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      expect(screen.queryByText('Select Directory')).not.toBeInTheDocument()
    })

    it('renders custom title', async () => {
      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          title="Select Backup Location"
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Select Backup Location')).toBeInTheDocument()
      })
    })

    it('shows search input', async () => {
      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Search...')).toBeInTheDocument()
      })
    })

    it('shows New Folder button', async () => {
      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /New Folder/i })).toBeInTheDocument()
      })
    })
  })

  describe('Directory Loading', () => {
    it('loads and displays directory items', async () => {
      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
        expect(screen.getByText('file.txt')).toBeInTheDocument()
        expect(screen.getByText('backup-repo')).toBeInTheDocument()
      })

      expect(api.get).toHaveBeenCalledWith('/filesystem/browse', {
        params: expect.objectContaining({
          path: '/',
          connection_type: 'local',
        }),
      })
    })

    it('shows loading state while fetching', async () => {
      const slowResolve = new Promise((resolve) =>
        setTimeout(() => resolve(mockDirectoryResponse), 100)
      )
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      vi.mocked(api.get).mockReturnValue(slowResolve as any)

      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      expect(screen.getByText('Loading...')).toBeInTheDocument()

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })
    })

    it('displays error message on API failure', async () => {
      vi.mocked(api.get).mockRejectedValue({
        response: { data: { detail: 'Permission denied' } },
      })

      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('Permission denied')).toBeInTheDocument()
      })
    })

    it('shows empty state when directory has no items', async () => {
      vi.mocked(api.get).mockResolvedValue(mockEmptyDirectoryResponse)

      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('No items found')).toBeInTheDocument()
        expect(screen.getByText('Empty directory')).toBeInTheDocument()
      })
    })
  })

  describe('Navigation', () => {
    it('navigates into directory when clicked', async () => {
      const user = userEvent.setup()
      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      const documentsFolder = screen.getByText('Documents')
      await user.click(documentsFolder)

      expect(api.get).toHaveBeenCalledWith('/filesystem/browse', {
        params: expect.objectContaining({
          path: '/home/user/Documents',
        }),
      })
    })

    it('navigates using breadcrumbs', async () => {
      const user = userEvent.setup()

      vi.mocked(api.get).mockResolvedValue({
        data: {
          current_path: '/home/user/Documents',
          items: [],
          is_inside_local_mount: false,
        },
      })

      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          initialPath="/home/user/Documents"
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Root')).toBeInTheDocument()
        expect(screen.getByText('home')).toBeInTheDocument()
        expect(screen.getByText('user')).toBeInTheDocument()
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      // Click on 'home' breadcrumb
      await user.click(screen.getByText('home'))

      expect(api.get).toHaveBeenCalledWith('/filesystem/browse', {
        params: expect.objectContaining({
          path: '/home',
        }),
      })
    })
  })

  describe('Search Functionality', () => {
    it('filters items based on search term', async () => {
      const user = userEvent.setup()

      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
        expect(screen.getByText('file.txt')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Search...')
      await user.type(searchInput, 'doc')

      expect(screen.getByText('Documents')).toBeInTheDocument()
      expect(screen.queryByText('file.txt')).not.toBeInTheDocument()
    })

    it('shows appropriate message when search has no results', async () => {
      const user = userEvent.setup()

      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Search...')
      await user.type(searchInput, 'nonexistent')

      expect(screen.getByText('No items found')).toBeInTheDocument()
      expect(screen.getByText('Try a different search')).toBeInTheDocument()
    })
  })

  describe('Single Selection Mode', () => {
    it('displays items for selection', async () => {
      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      // In single select mode, items are clickable
      const documentsItem = screen.getByText('Documents')
      expect(documentsItem).toBeInTheDocument()
    })

    it('enables Select button when item is selected', async () => {
      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      // Initially, Select button should be disabled
      const selectButton = screen.getAllByRole('button', { name: /Select/i })[0]
      expect(selectButton).toBeDisabled()
    })

    it('calls onSelect with selected path on confirm', async () => {
      const user = userEvent.setup()

      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          selectMode="directories"
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      // Use the "Use Current" button to select current directory
      await user.click(screen.getByRole('button', { name: /Use Current/i }))

      expect(mockOnSelect).toHaveBeenCalledWith(['/home/user'])
      expect(mockOnClose).toHaveBeenCalled()
    })
  })

  describe('Multi-Selection Mode', () => {
    it('shows checkboxes in multi-select mode', async () => {
      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          multiSelect={true}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      const checkboxes = screen.getAllByRole('checkbox')
      expect(checkboxes.length).toBeGreaterThan(0)
    })

    it('selects multiple items', async () => {
      const user = userEvent.setup()

      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          multiSelect={true}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      const checkboxes = screen.getAllByRole('checkbox')
      await user.click(checkboxes[0])
      await user.click(checkboxes[1])

      expect(screen.getByText('2 selected')).toBeInTheDocument()
    })

    it('deselects item when clicked again', async () => {
      const user = userEvent.setup()

      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          multiSelect={true}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      const checkboxes = screen.getAllByRole('checkbox')
      await user.click(checkboxes[0])
      expect(screen.getByText('1 selected')).toBeInTheDocument()

      await user.click(checkboxes[0])
      expect(screen.queryByText('1 selected')).not.toBeInTheDocument()
    })
  })

  describe('Select Mode', () => {
    it('only allows selecting directories in directory mode', async () => {
      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          multiSelect={true}
          selectMode="directories"
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
        expect(screen.getByText('file.txt')).toBeInTheDocument()
      })

      // File should not have a checkbox
      const allCheckboxes = screen.getAllByRole('checkbox')
      // Should have checkboxes only for directories (Documents and backup-repo)
      expect(allCheckboxes.length).toBe(2)
    })

    it('allows selecting both files and directories in both mode', async () => {
      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          multiSelect={true}
          selectMode="both"
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
        expect(screen.getByText('file.txt')).toBeInTheDocument()
      })

      // All items should have checkboxes
      const allCheckboxes = screen.getAllByRole('checkbox')
      expect(allCheckboxes.length).toBe(3) // Documents, file.txt, backup-repo
    })
  })

  describe('SSH Connections', () => {
    it('loads SSH connections at root', async () => {
      // Mock root directory response
      vi.mocked(api.get).mockResolvedValue({
        data: {
          current_path: '/',
          items: [],
          is_inside_local_mount: false,
        },
      })

      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          initialPath="/"
        />
      )

      await waitFor(() => {
        expect(sshKeysAPI.getSSHConnections).toHaveBeenCalled()
      })

      // Wait for mount point to appear
      await waitFor(
        () => {
          expect(screen.getByText('Remote Server')).toBeInTheDocument()
        },
        { timeout: 2000 }
      )
    })

    it('shows info alert about SSH connections at root', async () => {
      // Mock root directory response
      vi.mocked(api.get).mockResolvedValue({
        data: {
          current_path: '/',
          items: [],
          is_inside_local_mount: false,
        },
      })

      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          initialPath="/"
        />
      )

      await waitFor(
        () => {
          expect(screen.getByText(/SSH connections are shown below/i)).toBeInTheDocument()
        },
        { timeout: 2000 }
      )
    })

    it('switches to SSH mode when clicking mount point', async () => {
      const user = userEvent.setup()

      // Mock root directory response
      vi.mocked(api.get).mockResolvedValue({
        data: {
          current_path: '/',
          items: [],
          is_inside_local_mount: false,
        },
      })

      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          initialPath="/"
        />
      )

      await waitFor(
        () => {
          expect(screen.getByText('Remote Server')).toBeInTheDocument()
        },
        { timeout: 2000 }
      )

      await user.click(screen.getByText('Remote Server'))

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith('/filesystem/browse', {
          params: expect.objectContaining({
            connection_type: 'ssh',
            ssh_key_id: 1,
            host: 'remote.server.com',
            username: 'user',
            port: 22,
          }),
        })
      })
    })

    it('shows SSH connection chip when browsing via SSH', async () => {
      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          connectionType="ssh"
          sshConfig={{
            ssh_key_id: 1,
            host: 'remote.server.com',
            username: 'user',
            port: 22,
          }}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('user@remote.server.com')).toBeInTheDocument()
      })
    })
  })

  describe('Create Folder', () => {
    it('opens create folder dialog', async () => {
      const user = userEvent.setup()

      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: /New Folder/i }))

      expect(screen.getByText('Create New Folder')).toBeInTheDocument()
      expect(screen.getByLabelText('Folder Name')).toBeInTheDocument()
    })

    it('creates folder successfully', async () => {
      const user = userEvent.setup()
      vi.mocked(api.post).mockResolvedValue({ data: { success: true } })

      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: /New Folder/i }))

      const input = screen.getByLabelText('Folder Name')
      await user.type(input, 'NewFolder')

      const createButton = screen.getAllByRole('button', { name: /Create/i })[0]
      await user.click(createButton)

      expect(api.post).toHaveBeenCalledWith(
        '/filesystem/create-folder',
        expect.objectContaining({
          folder_name: 'NewFolder',
          path: '/home/user',
          connection_type: 'local',
        })
      )
    })

    it('shows error when folder creation fails', async () => {
      const user = userEvent.setup()
      vi.mocked(api.post).mockRejectedValueOnce({
        response: { data: { detail: 'Folder already exists' } },
      })

      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: /New Folder/i }))

      const input = screen.getByLabelText('Folder Name')
      await user.type(input, 'ExistingFolder')

      const createButton = screen.getAllByRole('button', { name: /Create/i })[0]
      await user.click(createButton)

      await waitFor(
        () => {
          // Error appears in both dialogs (main and create folder), so use getAllByText
          const errorMessages = screen.getAllByText('Folder already exists')
          expect(errorMessages.length).toBeGreaterThan(0)
        },
        { timeout: 2000 }
      )
    })

    it('disables Create button when folder name is empty', async () => {
      const user = userEvent.setup()

      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: /New Folder/i }))

      const createButton = screen.getAllByRole('button', { name: /Create/i })[0]
      expect(createButton).toBeDisabled()
    })

    it('creates folder on Enter key press', async () => {
      const user = userEvent.setup()
      vi.mocked(api.post).mockResolvedValue({ data: { success: true } })

      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: /New Folder/i }))

      const input = screen.getByLabelText('Folder Name')
      await user.type(input, 'NewFolder{Enter}')

      expect(api.post).toHaveBeenCalled()
    })
  })

  describe('Dialog Actions', () => {
    it('closes dialog on Cancel', async () => {
      const user = userEvent.setup()

      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: /Cancel/i }))

      expect(mockOnClose).toHaveBeenCalled()
    })

    it('shows Use Current button in directory mode', async () => {
      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          selectMode="directories"
        />
      )

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Use Current/i })).toBeInTheDocument()
      })
    })

    it('does not show Use Current button in files mode', async () => {
      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          selectMode="files"
        />
      )

      await waitFor(() => {
        expect(screen.queryByRole('button', { name: /Use Current/i })).not.toBeInTheDocument()
      })
    })
  })

  describe('Item Display', () => {
    it('shows Borg chip for borg repositories', async () => {
      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('backup-repo')).toBeInTheDocument()
      })

      const borgChip = screen.getByText('Borg')
      expect(borgChip).toBeInTheDocument()
    })

    it('shows file size for files', async () => {
      renderWithProviders(
        <FileExplorerDialog open={true} onClose={mockOnClose} onSelect={mockOnSelect} />
      )

      await waitFor(() => {
        expect(screen.getByText('file.txt')).toBeInTheDocument()
        expect(screen.getByText('1.0 KB')).toBeInTheDocument()
      })
    })

    it('shows Remote chip for mount points', async () => {
      // Mock root directory response
      vi.mocked(api.get).mockResolvedValue({
        data: {
          current_path: '/',
          items: [],
          is_inside_local_mount: false,
        },
      })

      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          initialPath="/"
        />
      )

      await waitFor(
        () => {
          expect(screen.getByText('Remote')).toBeInTheDocument()
        },
        { timeout: 2000 }
      )
    })
  })

  describe('Integration Tests', () => {
    it('completes full directory navigation and selection flow', async () => {
      const user = userEvent.setup()

      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          selectMode="directories"
        />
      )

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      // Select current directory
      await user.click(screen.getByRole('button', { name: /Use Current/i }))

      expect(mockOnSelect).toHaveBeenCalledWith(['/home/user'])
      expect(mockOnClose).toHaveBeenCalled()
    })

    it('completes multi-select flow', async () => {
      const user = userEvent.setup()

      renderWithProviders(
        <FileExplorerDialog
          open={true}
          onClose={mockOnClose}
          onSelect={mockOnSelect}
          multiSelect={true}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Documents')).toBeInTheDocument()
      })

      // Select multiple items
      const checkboxes = screen.getAllByRole('checkbox')
      await user.click(checkboxes[0])
      await user.click(checkboxes[1])

      expect(screen.getByText('2 selected')).toBeInTheDocument()

      // Confirm selection
      const selectButton = screen.getAllByRole('button', { name: /Select \(2\)/i })[0]
      await user.click(selectButton)

      expect(mockOnSelect).toHaveBeenCalledWith(['/home/user/Documents', '/home/user/backup-repo'])
      expect(mockOnClose).toHaveBeenCalled()
    })
  })
})
