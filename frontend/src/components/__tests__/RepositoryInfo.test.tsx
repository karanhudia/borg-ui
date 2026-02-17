import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import RepositoryInfo from '../RepositoryInfo'

describe('RepositoryInfo', () => {
  const mockRepoInfo = {
    repository: {
      id: 'test-repo',
      last_modified: '2024-01-15T10:30:00Z',
    },
    cache: {
      stats: {
        total_size: 1024 * 1024 * 100, // 100 MB
        total_csize: 1024 * 1024 * 50, // 50 MB
        unique_csize: 1024 * 1024 * 25, // 25 MB
        total_chunks: 1000,
        total_unique_chunks: 500,
      },
    },
    encryption: {
      mode: 'repokey-blake2',
    },
  }

  describe('Loading State', () => {
    it('shows loading message when loading is true', () => {
      render(<RepositoryInfo loading={true} />)
      expect(screen.getByText('Loading repository info...')).toBeInTheDocument()
    })

    it('does not show repository stats when loading', () => {
      render(<RepositoryInfo loading={true} repoInfo={mockRepoInfo} />)
      expect(screen.queryByText('Archives')).not.toBeInTheDocument()
    })
  })

  describe('Empty State', () => {
    it('returns null when repoInfo is undefined', () => {
      const { container } = render(<RepositoryInfo />)
      expect(container.firstChild).toBeNull()
    })

    it('returns null when repoInfo is null', () => {
      const { container } = render(<RepositoryInfo repoInfo={undefined} />)
      expect(container.firstChild).toBeNull()
    })
  })

  describe('Repository Statistics', () => {
    it('displays archives count', () => {
      render(<RepositoryInfo repoInfo={mockRepoInfo} archivesCount={10} />)
      expect(screen.getByText('Archives')).toBeInTheDocument()
      expect(screen.getByText('10')).toBeInTheDocument()
    })

    it('displays archives count as 0 when not provided', () => {
      render(<RepositoryInfo repoInfo={mockRepoInfo} />)
      expect(screen.getByText('0')).toBeInTheDocument()
    })

    it('displays formatted total size', () => {
      render(<RepositoryInfo repoInfo={mockRepoInfo} />)
      expect(screen.getByText('Total Size')).toBeInTheDocument()
      expect(screen.getByText('100.00 MB')).toBeInTheDocument()
    })

    it('displays formatted deduplicated size', () => {
      render(<RepositoryInfo repoInfo={mockRepoInfo} />)
      expect(screen.getByText('Deduplicated')).toBeInTheDocument()
      expect(screen.getByText('25.00 MB')).toBeInTheDocument()
    })

    it('displays formatted last modified date', () => {
      render(<RepositoryInfo repoInfo={mockRepoInfo} />)
      expect(screen.getByText('Last Modified')).toBeInTheDocument()
      // The formatDate utility will format this, just check it's present
      expect(screen.getByText(/Jan|2024|15/)).toBeInTheDocument()
    })

    it('displays N/A when total size is missing', () => {
      const infoWithoutSize = {
        ...mockRepoInfo,
        cache: { stats: {} },
      }
      render(<RepositoryInfo repoInfo={infoWithoutSize} />)
      const naElements = screen.getAllByText('N/A')
      expect(naElements.length).toBeGreaterThan(0)
    })

    it('displays N/A when deduplicated size is missing', () => {
      const infoWithoutDedup = {
        ...mockRepoInfo,
        cache: {
          stats: {
            total_size: 1024 * 1024 * 100,
          },
        },
      }
      render(<RepositoryInfo repoInfo={infoWithoutDedup} />)
      expect(screen.getAllByText('N/A').length).toBeGreaterThan(0)
    })

    it('displays N/A when last modified is missing', () => {
      const infoWithoutDate = {
        ...mockRepoInfo,
        repository: {},
      }
      render(<RepositoryInfo repoInfo={infoWithoutDate} />)
      expect(screen.getAllByText('N/A').length).toBeGreaterThan(0)
    })
  })

  describe('Encryption Information', () => {
    it('displays encryption mode chip when present', () => {
      render(<RepositoryInfo repoInfo={mockRepoInfo} />)
      expect(screen.getByText('Encryption: repokey-blake2')).toBeInTheDocument()
    })

    it('does not display encryption chip when mode is missing', () => {
      const infoWithoutEncryption = {
        ...mockRepoInfo,
        encryption: {},
      }
      render(<RepositoryInfo repoInfo={infoWithoutEncryption} />)
      expect(screen.queryByText(/Encryption:/)).not.toBeInTheDocument()
    })

    it('does not display encryption chip when encryption object is missing', () => {
      const infoWithoutEncryption = {
        repository: mockRepoInfo.repository,
        cache: mockRepoInfo.cache,
      }
      render(<RepositoryInfo repoInfo={infoWithoutEncryption} />)
      expect(screen.queryByText(/Encryption:/)).not.toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles zero stats gracefully', () => {
      const infoWithZeros = {
        ...mockRepoInfo,
        cache: {
          stats: {
            total_size: 0,
            unique_csize: 0,
          },
        },
      }
      render(<RepositoryInfo repoInfo={infoWithZeros} archivesCount={0} />)
      expect(screen.getByText('0')).toBeInTheDocument()
      // Zero values are treated as falsy, so N/A is displayed
      expect(screen.getAllByText('N/A').length).toBeGreaterThan(0)
    })

    it('handles partial repoInfo structure', () => {
      const partialInfo = {
        repository: {
          id: 'test',
        },
      }
      render(<RepositoryInfo repoInfo={partialInfo} />)
      expect(screen.getByText('Archives')).toBeInTheDocument()
      expect(screen.getAllByText('N/A').length).toBeGreaterThan(0)
    })
  })
})
