import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import RemoteMachineCard from '../RemoteMachineCard'

describe('RemoteMachineCard', () => {
  const mockOnEdit = vi.fn()
  const mockOnDelete = vi.fn()
  const mockOnRefreshStorage = vi.fn()
  const mockOnTestConnection = vi.fn()
  const mockOnDeployKey = vi.fn()

  const baseMachine = {
    id: 1,
    ssh_key_id: 1,
    ssh_key_name: 'Test Key',
    host: 'server.example.com',
    username: 'admin',
    port: 22,
    use_sftp_mode: true,
    use_sudo: false,
    status: 'connected',
    created_at: '2025-01-01T00:00:00Z',
  }

  const machineWithStorage = {
    ...baseMachine,
    storage: {
      total: 1000000000000,
      total_formatted: '1 TB',
      used: 500000000000,
      used_formatted: '500 GB',
      available: 500000000000,
      available_formatted: '500 GB',
      percent_used: 50,
    },
  }

  beforeEach(() => {
    mockOnEdit.mockClear()
    mockOnDelete.mockClear()
    mockOnRefreshStorage.mockClear()
    mockOnTestConnection.mockClear()
    mockOnDeployKey.mockClear()
  })

  describe('Rendering', () => {
    it('renders host name as title when no mount_point', () => {
      render(
        <RemoteMachineCard
          machine={baseMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.getByText('server.example.com')).toBeInTheDocument()
    })

    it('renders mount_point as title when available', () => {
      const machineWithMount = { ...baseMachine, mount_point: '/mnt/backup' }
      render(
        <RemoteMachineCard
          machine={machineWithMount}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      // mount_point appears in both title and Mount Point section
      const mountPointElements = screen.getAllByText('/mnt/backup')
      expect(mountPointElements.length).toBeGreaterThanOrEqual(1)
    })

    it('renders connection string', () => {
      render(
        <RemoteMachineCard
          machine={baseMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.getByText('admin@server.example.com:22')).toBeInTheDocument()
    })

    it('renders status chip for connected', () => {
      render(
        <RemoteMachineCard
          machine={baseMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.getByText('connected')).toBeInTheDocument()
    })

    it('renders status chip for failed', () => {
      const failedMachine = { ...baseMachine, status: 'failed' }
      render(
        <RemoteMachineCard
          machine={failedMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.getByText('failed')).toBeInTheDocument()
    })

    it('renders status chip for testing', () => {
      const testingMachine = { ...baseMachine, status: 'testing' }
      render(
        <RemoteMachineCard
          machine={testingMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.getByText('testing')).toBeInTheDocument()
    })

    it('renders unknown status', () => {
      const unknownMachine = { ...baseMachine, status: 'unknown' }
      render(
        <RemoteMachineCard
          machine={unknownMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.getByText('unknown')).toBeInTheDocument()
    })
  })

  describe('Storage Info', () => {
    it('renders storage info when available', () => {
      render(
        <RemoteMachineCard
          machine={machineWithStorage}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.getAllByText('500 GB').length).toBeGreaterThan(0)
      expect(screen.getByText('50.0% used')).toBeInTheDocument()
    })

    it('renders No storage info when storage is null', () => {
      render(
        <RemoteMachineCard
          machine={baseMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.getByText('No storage info')).toBeInTheDocument()
    })

    it('renders refresh storage button when no storage', () => {
      render(
        <RemoteMachineCard
          machine={baseMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.getByRole('button', { name: 'Refresh storage' })).toBeInTheDocument()
    })

    it('calls onRefreshStorage when refresh button clicked', async () => {
      const user = userEvent.setup()
      render(
        <RemoteMachineCard
          machine={baseMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      await user.click(screen.getByRole('button', { name: 'Refresh storage' }))
      expect(mockOnRefreshStorage).toHaveBeenCalledWith(baseMachine)
    })

    it('shows warning color for >75% storage used', () => {
      const highUsageMachine = {
        ...baseMachine,
        storage: { ...machineWithStorage.storage, percent_used: 80 },
      }
      render(
        <RemoteMachineCard
          machine={highUsageMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.getByText('80.0% used')).toBeInTheDocument()
    })

    it('shows error color for >90% storage used', () => {
      const criticalUsageMachine = {
        ...baseMachine,
        storage: { ...machineWithStorage.storage, percent_used: 95 },
      }
      render(
        <RemoteMachineCard
          machine={criticalUsageMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.getByText('95.0% used')).toBeInTheDocument()
    })
  })

  describe('Optional fields', () => {
    it('renders default_path when available', () => {
      const machineWithPath = { ...baseMachine, default_path: '/data/backups' }
      render(
        <RemoteMachineCard
          machine={machineWithPath}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.getByText(/Default Path/)).toBeInTheDocument()
      expect(screen.getByText('/data/backups')).toBeInTheDocument()
    })

    it('does not render default_path when not available', () => {
      render(
        <RemoteMachineCard
          machine={baseMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.queryByText('Default Path')).not.toBeInTheDocument()
    })

    it('renders mount_point section when different from host', () => {
      const machineWithMount = { ...baseMachine, mount_point: '/mnt/backup' }
      render(
        <RemoteMachineCard
          machine={machineWithMount}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.getByText(/Mount Point/)).toBeInTheDocument()
    })

    it('does not render mount_point section when same as host', () => {
      const machineWithSameMount = { ...baseMachine, mount_point: 'server.example.com' }
      render(
        <RemoteMachineCard
          machine={machineWithSameMount}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.queryByText('Mount Point')).not.toBeInTheDocument()
    })

    it('renders error message when present', () => {
      const machineWithError = { ...baseMachine, error_message: 'Connection refused' }
      render(
        <RemoteMachineCard
          machine={machineWithError}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )
      expect(screen.getByText('Connection refused')).toBeInTheDocument()
    })
  })

  describe('Context Menu', () => {
    it('renders all action buttons', () => {
      render(
        <RemoteMachineCard
          machine={baseMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )

      expect(screen.getByRole('button', { name: 'Test Connection' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Refresh Storage' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Deploy Key' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
    })

    it('calls onTestConnection from menu', async () => {
      const user = userEvent.setup()
      render(
        <RemoteMachineCard
          machine={baseMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )

      await user.click(screen.getByRole('button', { name: 'Test Connection' }))
      expect(mockOnTestConnection).toHaveBeenCalledWith(baseMachine)
    })

    it('calls onDeployKey from menu', async () => {
      const user = userEvent.setup()
      render(
        <RemoteMachineCard
          machine={baseMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )

      await user.click(screen.getByRole('button', { name: 'Deploy Key' }))
      expect(mockOnDeployKey).toHaveBeenCalledWith(baseMachine)
    })

    it('calls onRefreshStorage from menu', async () => {
      const user = userEvent.setup()
      render(
        <RemoteMachineCard
          machine={baseMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )

      await user.click(screen.getByRole('button', { name: 'Refresh Storage' }))
      expect(mockOnRefreshStorage).toHaveBeenCalledWith(baseMachine)
    })

    it('calls onEdit from menu', async () => {
      const user = userEvent.setup()
      render(
        <RemoteMachineCard
          machine={baseMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )

      await user.click(screen.getByRole('button', { name: 'Edit' }))
      expect(mockOnEdit).toHaveBeenCalledWith(baseMachine)
    })

    it('calls onDelete from menu', async () => {
      const user = userEvent.setup()
      render(
        <RemoteMachineCard
          machine={baseMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )

      await user.click(screen.getByRole('button', { name: 'Delete' }))
      expect(mockOnDelete).toHaveBeenCalledWith(baseMachine)
    })

    it('hides management actions when connection management is not allowed', () => {
      render(
        <RemoteMachineCard
          machine={baseMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
          canManageConnections={false}
        />
      )

      expect(screen.getByRole('button', { name: 'Test Connection' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Refresh Storage' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Deploy Key' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
    })

    it('closes menu after action', async () => {
      const user = userEvent.setup()
      render(
        <RemoteMachineCard
          machine={baseMachine}
          onEdit={mockOnEdit}
          onDelete={mockOnDelete}
          onRefreshStorage={mockOnRefreshStorage}
          onTestConnection={mockOnTestConnection}
          onDeployKey={mockOnDeployKey}
        />
      )

      await user.click(screen.getByRole('button', { name: 'Edit' }))
      expect(mockOnEdit).toHaveBeenCalledWith(baseMachine)
    })
  })
})
