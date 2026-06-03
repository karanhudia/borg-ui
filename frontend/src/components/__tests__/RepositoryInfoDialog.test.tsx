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
}

const mockRepositoryInfo = {
  encryption: {
    mode: 'repokey-blake2',
  },
  repository: {
    last_modified: '2024-01-15T10:30:00Z',
    location: '/backups/test-repo',
  },
  cache: {
    stats: {
      total_size: 1073741824, // 1 GB
      unique_size: 536870912, // 512 MB
      unique_csize: 268435456, // 256 MB
      total_chunks: 10000,
      total_unique_chunks: 5000,
    },
  },
}

describe('RepositoryInfoDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockCanUseFeature.mockReturnValue(true)
  })

  describe('Rendering', () => {
    it('renders dialog when open', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={mockRepositoryInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText('Test Repository')).toBeInTheDocument()
    })

    it('does not render when closed', () => {
      render(
        <RepositoryInfoDialog
          open={false}
          repository={mockRepository}
          repositoryInfo={mockRepositoryInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      expect(screen.queryByText('Test Repository')).not.toBeInTheDocument()
    })
  })

  describe('Loading State', () => {
    it('shows loading message when loading', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={null}
          isLoading={true}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText('Loading repository info...')).toBeInTheDocument()
    })
  })

  describe('Repository Details', () => {
    it('shows encryption mode', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={mockRepositoryInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText('Encryption')).toBeInTheDocument()
      expect(screen.getByText('repokey-blake2')).toBeInTheDocument()
    })

    it('shows last modified date', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={mockRepositoryInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText('Last Modified')).toBeInTheDocument()
    })

    it('shows repository location', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={mockRepositoryInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText('Repository Location')).toBeInTheDocument()
      expect(screen.getByText('/backups/test-repo')).toBeInTheDocument()
    })
  })

  describe('Storage Statistics', () => {
    it('shows storage statistics header', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={mockRepositoryInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText('Storage Statistics')).toBeInTheDocument()
    })

    it('shows total size', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={mockRepositoryInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText('Total Size')).toBeInTheDocument()
    })

    it('shows unique data', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={mockRepositoryInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText('Unique Data')).toBeInTheDocument()
    })

    it('shows used on disk', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={mockRepositoryInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText('Used on Disk')).toBeInTheDocument()
    })

    it('shows chunk statistics', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={mockRepositoryInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText('Total Chunks')).toBeInTheDocument()
      expect(screen.getByText('10,000')).toBeInTheDocument()
      expect(screen.getByText('Unique Chunks')).toBeInTheDocument()
      expect(screen.getByText('5,000')).toBeInTheDocument()
    })
  })

  describe('Empty Repository', () => {
    it('shows no backups message when stats are empty', () => {
      const emptyRepoInfo = {
        encryption: { mode: 'repokey' },
        repository: { location: '/backups/test' },
        cache: {
          stats: {
            total_size: 0,
            unique_size: 0,
            unique_csize: 0,
            total_chunks: 0,
            total_unique_chunks: 0,
          },
        },
      }

      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={emptyRepoInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText('No backups yet')).toBeInTheDocument()
    })

    it('shows explanation for empty repository', () => {
      const emptyRepoInfo = {
        encryption: { mode: 'repokey' },
        repository: { location: '/backups/test' },
        cache: {
          stats: {
            total_size: 0,
            unique_size: 0,
            unique_csize: 0,
            total_chunks: 0,
            total_unique_chunks: 0,
          },
        },
      }

      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={emptyRepoInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText(/contains no archives/i)).toBeInTheDocument()
    })
  })

  describe('Error State', () => {
    it('shows error message when repository info is null', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={null}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByText(/Failed to load repository information/i)).toBeInTheDocument()
    })

    it('shows copyable recovery commands when repository info cannot load', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={{ ...mockRepository, encryption: 'repokey', borg_version: 1 }}
          repositoryInfo={null}
          isLoading={false}
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
          repositoryInfo={null}
          isLoading={false}
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
          repositoryInfo={null}
          isLoading={false}
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
          repositoryInfo={null}
          isLoading={false}
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
          repositoryInfo={null}
          isLoading={false}
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
          repositoryInfo={null}
          isLoading={false}
          onClose={vi.fn()}
          onRunRecoveryCheck={vi.fn()}
          canRunRecoveryCheck={false}
        />
      )

      expect(screen.getByRole('button', { name: 'Run guided check' })).toBeDisabled()
      expect(screen.getByText('Maintenance access is required to run checks in Borg UI.')).toBeInTheDocument()
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
          repositoryInfo={null}
          isLoading={false}
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
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={mockRepositoryInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      expect(screen.getByRole('button', { name: /Close/i })).toBeInTheDocument()
    })

    it('calls onClose when Close is clicked', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()

      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={mockRepositoryInfo}
          isLoading={false}
          onClose={onClose}
        />
      )

      await user.click(screen.getByRole('button', { name: /Close/i }))

      expect(onClose).toHaveBeenCalled()
    })
  })

  describe('Borg 2 repository stats', () => {
    const v2Repo = { id: 2, name: 'V2 Repo', path: '/repo/test', borg_version: 2 }
    const v2Info = {
      encryption: { mode: 'repokey-aes-ocb' },
      repository: { location: '/backups/v2' },
      archives: [
        {
          name: 'arch-1',
          time: '2024-01-01T10:00:00Z',
          stats: { original_size: 2 * 1024 * 1024 * 1024, nfiles: 1000 },
        },
        {
          name: 'arch-2',
          time: '2024-06-01T10:00:00Z',
          stats: { original_size: 4 * 1024 * 1024 * 1024, nfiles: 2500 },
        },
      ],
    }

    it('renders archive count for v2 repo', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={v2Repo}
          repositoryInfo={v2Info}
          isLoading={false}
          onClose={vi.fn()}
        />
      )
      expect(screen.getByText('2')).toBeInTheDocument()
    })

    it('renders file count from latest archive for v2 repo', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={v2Repo}
          repositoryInfo={v2Info}
          isLoading={false}
          onClose={vi.fn()}
        />
      )
      expect(screen.getByText('2,500')).toBeInTheDocument()
    })

    it('does not render v1 chunk count labels for v2 repo', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={v2Repo}
          repositoryInfo={v2Info}
          isLoading={false}
          onClose={vi.fn()}
        />
      )
      expect(screen.queryByText('Total Chunks')).not.toBeInTheDocument()
      expect(screen.queryByText('Unique Chunks')).not.toBeInTheDocument()
    })

    it('shows no backups alert for v2 repo with empty archives', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={v2Repo}
          repositoryInfo={{ ...v2Info, archives: [] }}
          isLoading={false}
          onClose={vi.fn()}
        />
      )
      expect(screen.getByText('No backups yet')).toBeInTheDocument()
    })
  })

  describe('Keyfile download API', () => {
    const keyfileRepo = { id: 5, name: 'Keyfile Repo', path: '/repo/test', has_keyfile: true }

    it('shows export keyfile button when has_keyfile is true', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={keyfileRepo}
          repositoryInfo={mockRepositoryInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )
      expect(screen.getByRole('button', { name: /export keyfile/i })).toBeInTheDocument()
    })

    it('does not show export button when has_keyfile is false', () => {
      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={mockRepositoryInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )
      expect(screen.queryByRole('button', { name: /export keyfile/i })).not.toBeInTheDocument()
    })

    it('calls repositoriesAPI.downloadKeyfile with correct repo id on click', async () => {
      const blob = new Blob(['keydata'], { type: 'application/octet-stream' })
      vi.mocked(repositoriesAPI.downloadKeyfile).mockResolvedValue({ data: blob } as Awaited<
        ReturnType<typeof repositoriesAPI.downloadKeyfile>
      >)
      URL.createObjectURL = vi.fn().mockReturnValue('blob:test')
      URL.revokeObjectURL = vi.fn()

      render(
        <RepositoryInfoDialog
          open={true}
          repository={keyfileRepo}
          repositoryInfo={mockRepositoryInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /export keyfile/i }))

      await waitFor(() => {
        expect(repositoriesAPI.downloadKeyfile).toHaveBeenCalledWith(keyfileRepo.id)
      })
    })
  })

  describe('N/A Values', () => {
    it('shows N/A for missing encryption', () => {
      const noEncryptionInfo = {
        encryption: {},
        repository: { location: '/backups/test' },
        cache: { stats: { unique_size: 100 } },
      }

      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={noEncryptionInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      // Multiple N/A values possible when encryption or last_modified missing
      const naElements = screen.getAllByText('N/A')
      expect(naElements.length).toBeGreaterThanOrEqual(1)
    })

    it('shows N/A for missing location', () => {
      const noLocationInfo = {
        encryption: { mode: 'repokey' },
        repository: {},
        cache: { stats: { unique_size: 100 } },
      }

      render(
        <RepositoryInfoDialog
          open={true}
          repository={mockRepository}
          repositoryInfo={noLocationInfo}
          isLoading={false}
          onClose={vi.fn()}
        />
      )

      const naElements = screen.getAllByText('N/A')
      expect(naElements.length).toBeGreaterThanOrEqual(1)
    })
  })
})
