import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import RepositoryInfoDialog from '../RepositoryInfoDialog'

const { mockCanUseFeature } = vi.hoisted(() => ({
  mockCanUseFeature: vi.fn(() => true),
}))

vi.mock('../../services/api', () => ({
  repositoriesAPI: {
    downloadKeyfile: vi.fn(),
  },
}))

vi.mock('../../hooks/usePlan', () => ({
  usePlan: () => ({
    plan: 'community',
    isLoading: false,
    can: mockCanUseFeature,
  }),
}))

import { repositoriesAPI } from '../../services/api'

const mockRepository = {
  id: 1,
  name: 'Test Repository',
  path: '/repo/test',
  encryption: 'repokey-blake2',
}

const storedBorg1 = {
  size_bytes: 268435456, // 256 MB
  size_source: 'borg1_cache_stats' as const,
  measured_at: '2024-01-15T10:35:00Z',
  last_modified: '2024-01-15T10:30:00Z',
  archives_consistent: true,
  archives_listed: true,
  original_size: 1073741824, // 1 GB
  compressed_size: 536870912, // 512 MB
  deduplicated_size: 268435456,
  latest_archive_files: 10000,
  first_backup_at: '2023-11-01T10:30:00Z',
  last_backup_at: '2024-01-15T10:30:00Z',
  compact: null,
  compact_at: null,
}

const storedBorg2 = {
  size_bytes: 6 * 1024 * 1024 * 1024,
  size_source: 'borg2_index' as const,
  measured_at: '2024-06-01T10:05:00Z',
  last_modified: '2024-06-01T10:00:00Z',
  archives_consistent: true,
  archives_listed: true,
  original_size: 6 * 1024 * 1024 * 1024,
  compressed_size: null,
  deduplicated_size: 2 * 1024 * 1024 * 1024,
  latest_archive_files: 2500,
  first_backup_at: '2024-05-01T10:00:00Z',
  last_backup_at: '2024-06-01T10:00:00Z',
  compact: {
    source_size: 6 * 1024 * 1024 * 1024,
    deduplicated_size: 2 * 1024 * 1024 * 1024,
    compression_factor: 1.5,
    deduplication_factor: 3,
    size_precision: 'exact',
  },
  compact_at: '2024-06-01T09:00:00Z',
}

const unmeasured = {
  size_bytes: null,
  size_source: null,
  measured_at: null,
  last_modified: null,
  archives_consistent: false,
  archives_listed: false,
  original_size: null,
  compressed_size: null,
  deduplicated_size: null,
  latest_archive_files: null,
  first_backup_at: null,
  last_backup_at: null,
  compact: null,
  compact_at: null,
}

describe('RepositoryInfoDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockCanUseFeature.mockReturnValue(true)
  })

  describe('Rendering', () => {
    it('renders dialog when open', () => {
      render(<RepositoryInfoDialog open={true} repository={mockRepository} onClose={vi.fn()} />)

      expect(screen.getByText('Test Repository')).toBeInTheDocument()
    })

    it('does not render when closed', () => {
      render(<RepositoryInfoDialog open={false} repository={mockRepository} onClose={vi.fn()} />)

      expect(screen.queryByText('Test Repository')).not.toBeInTheDocument()
    })
  })

  describe('Refresh', () => {
    it('shows no refresh button without a handler', () => {
      render(<RepositoryInfoDialog open={true} repository={mockRepository} onClose={vi.fn()} />)
      expect(screen.queryByRole('button', { name: /Refresh from Borg/i })).not.toBeInTheDocument()
    })

    it('calls onRefresh from the header button', () => {
      const onRefresh = vi.fn()
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onRefresh={onRefresh}
        />
      )
      fireEvent.click(screen.getByRole('button', { name: /Refresh from Borg/i }))
      expect(onRefresh).toHaveBeenCalledTimes(1)
    })

    it('disables the button while a refresh runs and keeps the stored details up', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onRefresh={vi.fn()}
          isRefreshing={true}
        />
      )
      expect(screen.getByRole('button', { name: /Refresh from Borg/i })).toBeDisabled()
      expect(screen.getByText('repokey-blake2')).toBeInTheDocument()
    })
  })

  describe('Repository Details', () => {
    it('shows encryption mode', () => {
      render(<RepositoryInfoDialog open={true} repository={mockRepository} onClose={vi.fn()} />)

      expect(screen.getByText('Encryption')).toBeInTheDocument()
      expect(screen.getByText('repokey-blake2')).toBeInTheDocument()
    })

    it('shows the stored last modified date', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          storage={storedBorg1}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText('Last Modified')).toBeInTheDocument()
      expect(screen.queryByText('N/A')).not.toBeInTheDocument()
    })

    it('shows repository location', () => {
      render(<RepositoryInfoDialog open={true} repository={mockRepository} onClose={vi.fn()} />)

      expect(screen.getByText('Repository Location')).toBeInTheDocument()
      expect(screen.getByText('/repo/test')).toBeInTheDocument()
    })
  })

  describe('Storage Statistics', () => {
    it('shows the stored figures for a Borg 1 repository', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={{ ...mockRepository, borg_version: 1, archive_count: 25 }}
          storage={storedBorg1}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText('Storage Statistics')).toBeInTheDocument()
      expect(screen.getByTestId('repository-stat-usedOnDisk')).toHaveTextContent('Used on Disk')
      expect(screen.getByTestId('repository-stat-usedOnDisk')).toHaveTextContent('256.00 MB')
      expect(screen.getByTestId('repository-stat-originalSize')).toHaveTextContent('1.00 GB')
      expect(screen.getByTestId('repository-stat-spaceSaved')).toHaveTextContent('4.00×')
      expect(screen.getByTestId('repository-stat-archives')).toHaveTextContent('25')
      expect(screen.getByTestId('repository-stat-backupSpan')).toHaveTextContent('to')
      expect(screen.getByTestId('repository-stat-latestArchiveFiles')).toHaveTextContent('10,000')
      expect(screen.queryByText('Compressed')).not.toBeInTheDocument()
    })

    it('does not read the live cache statistics for the figures', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={{ ...mockRepository, borg_version: 1 }}
          storage={unmeasured}
          onClose={vi.fn()}
        />
      )

      // the live payload says 1 GB; the stored figures say nothing yet
      expect(screen.queryByText('1.00 GB')).not.toBeInTheDocument()
      expect(screen.getByTestId('repository-stat-usedOnDisk')).toHaveAttribute(
        'data-state',
        'unknown'
      )
      expect(screen.queryByText('0 B')).not.toBeInTheDocument()
    })

    it('shows the rows as unknown while the storage payload has not loaded', () => {
      render(<RepositoryInfoDialog open={true} repository={mockRepository} onClose={vi.fn()} />)

      expect(screen.getByText('Storage Statistics')).toBeInTheDocument()
      expect(screen.getAllByText('Unknown').length).toBeGreaterThan(0)
      expect(screen.queryByText('0 B')).not.toBeInTheDocument()
    })
  })

  describe('Empty Repository', () => {
    it('shows a measured zero for a repository whose archives were all pruned', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={{ ...mockRepository, borg_version: 1, archive_count: 0 }}
          storage={{ ...storedBorg1, original_size: 0, compressed_size: 0 }}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByTestId('repository-stat-originalSize')).toHaveTextContent('0 B')
      expect(screen.getByTestId('repository-stat-originalSize')).toHaveAttribute(
        'data-state',
        'value'
      )
    })

    it('says indexing while the post-import chain has not listed the archives', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={{
            ...mockRepository,
            borg_version: 2,
            archive_count: 0,
            index_pending_kinds: ['stats', 'archive_sync'],
          }}
          storage={unmeasured}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByTestId('repository-stat-usedOnDisk')).toHaveTextContent('Indexing…')
      expect(screen.getByTestId('repository-stat-originalSize')).toHaveTextContent('Indexing…')
      expect(screen.getByTestId('repository-stat-backupSpan')).toHaveTextContent('Indexing…')
    })
  })

  describe('Error State', () => {
    it('shows the stored figures under the error when the live info failed', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={{ ...mockRepository, borg_version: 1, archive_count: 25 }}
          refreshFailed
          storage={storedBorg1}
          onClose={vi.fn()}
        />
      )
      expect(screen.getByText(/Failed to load repository information/i)).toBeInTheDocument()
      expect(screen.getByTestId('repository-stat-usedOnDisk')).toHaveTextContent('256.00 MB')
    })

    it('shows error message when repository info is null', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          refreshFailed
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText(/Failed to load repository information/i)).toBeInTheDocument()
    })

    it('shows the backend failure reason under the generic error', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          refreshFailed
          onClose={vi.fn()}
          errorMessage="repository.info exited with code 2: Failed to create/acquire the lock (Permission denied)"
        />
      )

      expect(screen.getByText(/Failed to load repository information/i)).toBeInTheDocument()
      expect(screen.getByText(/Permission denied/)).toBeInTheDocument()
    })

    it('shows copyable recovery commands when repository info cannot load', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={{ ...mockRepository, encryption: 'repokey', borg_version: 1 }}
          refreshFailed
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText('Recovery commands')).toBeInTheDocument()
      expect(screen.getByText('borg check /repo/test')).toBeInTheDocument()
      expect(screen.getByText('borg check --repair /repo/test')).toBeInTheDocument()
      expect(screen.getByText('borg init --encryption repokey /repo/test')).toBeInTheDocument()
    })

    it('shell-escapes recovery command paths and remote path values', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={{
            ...mockRepository,
            encryption: 'repokey',
            borg_version: 1,
            path: '/repo/test path;rm',
            remote_path: '/usr/bin/borg 2',
          }}
          refreshFailed
          onClose={vi.fn()}
        />
      )

      expect(
        screen.getByText("borg check --remote-path '/usr/bin/borg 2' '/repo/test path;rm'")
      ).toBeInTheDocument()
      expect(
        screen.getByText("borg check --repair --remote-path '/usr/bin/borg 2' '/repo/test path;rm'")
      ).toBeInTheDocument()
      expect(
        screen.getByText(
          "borg init --encryption repokey --remote-path '/usr/bin/borg 2' '/repo/test path;rm'"
        )
      ).toBeInTheDocument()
    })

    it('shows recovery commands for Borg 2 repositories even when Borg 2 details are gated', () => {
      mockCanUseFeature.mockReturnValue(false)

      render(
        <RepositoryInfoDialog
          open={true}
          repository={{ ...mockRepository, encryption: 'repokey-aes-ocb', borg_version: 2 }}
          refreshFailed
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText(/Failed to load repository information/i)).toBeInTheDocument()
      expect(screen.getByText('Recovery commands')).toBeInTheDocument()
      expect(screen.getByText('borg2 -r /repo/test check')).toBeInTheDocument()
    })

    it('copies a recovery command to the clipboard', async () => {
      const user = userEvent.setup()
      const writeText = vi.fn().mockResolvedValue(undefined)
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText },
      })

      render(
        <RepositoryInfoDialog
          open={true}
          repository={{ ...mockRepository, encryption: 'repokey', borg_version: 1 }}
          refreshFailed
          onClose={vi.fn()}
        />
      )

      await user.click(screen.getByRole('button', { name: 'Copy Check repository command' }))

      expect(writeText).toHaveBeenCalledWith('borg check /repo/test')
    })

    it('runs the guided recovery check action when available', async () => {
      const user = userEvent.setup()
      const onRunRecoveryCheck = vi.fn()

      render(
        <RepositoryInfoDialog
          open={true}
          repository={{ ...mockRepository, encryption: 'repokey', borg_version: 1 }}
          refreshFailed
          onClose={vi.fn()}
          onRunRecoveryCheck={onRunRecoveryCheck}
          canRunRecoveryCheck={true}
        />
      )

      await user.click(screen.getByRole('button', { name: 'Run guided check' }))

      expect(onRunRecoveryCheck).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 1,
          name: 'Test Repository',
          path: '/repo/test',
        })
      )
      expect(screen.getByText('borg check /repo/test')).toBeInTheDocument()
      expect(screen.getByText('borg check --repair /repo/test')).toBeInTheDocument()
      expect(screen.getByText('borg init --encryption repokey /repo/test')).toBeInTheDocument()
    })

    it('keeps command fallbacks visible when guided recovery check is unavailable', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={{ ...mockRepository, encryption: 'repokey', borg_version: 1 }}
          refreshFailed
          onClose={vi.fn()}
          onRunRecoveryCheck={vi.fn()}
          canRunRecoveryCheck={false}
        />
      )

      expect(screen.getByRole('button', { name: 'Run guided check' })).toBeDisabled()
      expect(
        screen.getByText('Maintenance access is required to run checks in Borg UI.')
      ).toBeInTheDocument()
      expect(screen.getByText('borg check /repo/test')).toBeInTheDocument()
      expect(screen.getByText('borg check --repair /repo/test')).toBeInTheDocument()
      expect(screen.getByText('borg init --encryption repokey /repo/test')).toBeInTheDocument()
    })

    it('clears the copied feedback timeout when unmounted', async () => {
      const writeText = vi.fn().mockResolvedValue(undefined)
      const setTimeoutSpy = vi.spyOn(window, 'setTimeout')
      const clearTimeoutSpy = vi.spyOn(window, 'clearTimeout')
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText },
      })

      const { unmount } = render(
        <RepositoryInfoDialog
          open={true}
          repository={{ ...mockRepository, encryption: 'repokey', borg_version: 1 }}
          refreshFailed
          onClose={vi.fn()}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: 'Copy Check repository command' }))
      await waitFor(() => expect(writeText).toHaveBeenCalledWith('borg check /repo/test'))
      const copyTimeoutResult = setTimeoutSpy.mock.results.find(
        (_, index) => setTimeoutSpy.mock.calls[index]?.[1] === 2000
      )

      expect(copyTimeoutResult?.value).toBeDefined()

      unmount()

      expect(clearTimeoutSpy).toHaveBeenCalledWith(copyTimeoutResult?.value)
      setTimeoutSpy.mockRestore()
      clearTimeoutSpy.mockRestore()
    })
  })

  describe('Close Button', () => {
    it('renders Close button', () => {
      render(<RepositoryInfoDialog open={true} repository={mockRepository} onClose={vi.fn()} />)

      expect(screen.getByRole('button', { name: /Close/i })).toBeInTheDocument()
    })

    it('calls onClose when Close is clicked', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()

      render(<RepositoryInfoDialog open={true} repository={mockRepository} onClose={onClose} />)

      await user.click(screen.getByRole('button', { name: /Close/i }))

      expect(onClose).toHaveBeenCalled()
    })
  })

  describe('Borg 2 repository stats', () => {
    const v2Repo = {
      id: 2,
      name: 'V2 Repo',
      path: '/repo/test',
      borg_version: 2,
      encryption: 'repokey-aes-ocb',
    }

    it('keeps the stored figures behind the Borg 2 plan gate', () => {
      mockCanUseFeature.mockReturnValue(false)
      // a blocked gate reports itself, which needs the query client
      render(
        <QueryClientProvider client={new QueryClient()}>
          <RepositoryInfoDialog
            open={true}
            repository={v2Repo}
            storage={storedBorg2}
            onClose={vi.fn()}
          />
        </QueryClientProvider>
      )
      expect(screen.queryByTestId('repository-stat-usedOnDisk')).not.toBeInTheDocument()
      expect(screen.queryByText('Storage Statistics')).not.toBeInTheDocument()
    })

    it('shows a Borg 1 repository its figures on every plan', () => {
      mockCanUseFeature.mockReturnValue(false)
      render(
        <RepositoryInfoDialog
          open={true}
          repository={{ ...mockRepository, borg_version: 1 }}
          storage={storedBorg1}
          onClose={vi.fn()}
        />
      )
      expect(screen.getByTestId('repository-stat-usedOnDisk')).toHaveTextContent('256.00 MB')
    })

    it('shows the same rows as Borg 1, from the stored figures', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={v2Repo}
          storage={storedBorg2}
          onClose={vi.fn()}
        />
      )
      expect(screen.getByTestId('repository-stat-usedOnDisk')).toHaveTextContent('6.00 GB')
      expect(screen.getByTestId('repository-stat-spaceSaved')).toHaveTextContent('1.00×')
      expect(screen.queryByText(/not reported/i)).not.toBeInTheDocument()
      expect(screen.queryByText('Deduplicated Size')).not.toBeInTheDocument()
    })

    it('renders the file count of the newest archive', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={v2Repo}
          storage={storedBorg2}
          onClose={vi.fn()}
        />
      )
      expect(screen.getByText('2,500')).toBeInTheDocument()
    })

    it('shows the backup span and no compact statistics', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={v2Repo}
          storage={storedBorg2}
          onClose={vi.fn()}
        />
      )
      expect(screen.getByTestId('repository-stat-backupSpan')).toHaveAttribute(
        'data-state',
        'value'
      )
      expect(screen.queryByText('Last Compact')).not.toBeInTheDocument()
    })

    it('does not render v1 chunk count labels for v2 repo', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={v2Repo}
          storage={storedBorg2}
          onClose={vi.fn()}
        />
      )
      expect(screen.queryByText('Total Chunks')).not.toBeInTheDocument()
      expect(screen.queryByText('Unique Chunks')).not.toBeInTheDocument()
    })
  })

  describe('Keyfile download API', () => {
    const keyfileRepo = { id: 5, name: 'Keyfile Repo', path: '/repo/test', has_keyfile: true }

    it('shows export keyfile button when has_keyfile is true', () => {
      render(<RepositoryInfoDialog open={true} repository={keyfileRepo} onClose={vi.fn()} />)
      expect(screen.getByRole('button', { name: /export keyfile/i })).toBeInTheDocument()
    })

    it('does not show export button when has_keyfile is false', () => {
      render(<RepositoryInfoDialog open={true} repository={mockRepository} onClose={vi.fn()} />)
      expect(screen.queryByRole('button', { name: /export keyfile/i })).not.toBeInTheDocument()
    })

    it('calls repositoriesAPI.downloadKeyfile with correct repo id on click', async () => {
      const blob = new Blob(['keydata'], { type: 'application/octet-stream' })
      vi.mocked(repositoriesAPI.downloadKeyfile).mockResolvedValue({ data: blob } as Awaited<
        ReturnType<typeof repositoriesAPI.downloadKeyfile>
      >)
      URL.createObjectURL = vi.fn().mockReturnValue('blob:test')
      URL.revokeObjectURL = vi.fn()

      render(<RepositoryInfoDialog open={true} repository={keyfileRepo} onClose={vi.fn()} />)

      fireEvent.click(screen.getByRole('button', { name: /export keyfile/i }))

      await waitFor(() => {
        expect(repositoriesAPI.downloadKeyfile).toHaveBeenCalledWith(keyfileRepo.id)
      })
    })
  })

  describe('N/A Values', () => {
    it('shows N/A for a row without a stored encryption mode', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={{ ...mockRepository, encryption: undefined }}
          storage={storedBorg1}
          onClose={vi.fn()}
        />
      )

      expect(screen.getAllByText('N/A')).toHaveLength(1)
    })

    it('shows N/A for last modified while nothing has measured the repository', () => {
      render(<RepositoryInfoDialog open={true} repository={mockRepository} onClose={vi.fn()} />)

      expect(screen.getAllByText('N/A')).toHaveLength(1)
    })
  })
})
