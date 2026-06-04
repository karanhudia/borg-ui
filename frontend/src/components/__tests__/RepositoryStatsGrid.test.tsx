import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import RepositoryStatsGrid from '../RepositoryStatsGrid'

describe('RepositoryStatsGrid', () => {
  const mockStats = {
    original_size: 5368709120, // 5 GB
    compressed_size: 2147483648, // 2 GB
    deduplicated_size: 1073741824, // 1 GB
  }

  it('renders all stat cards', () => {
    render(<RepositoryStatsGrid stats={mockStats} archivesCount={10} />)

    expect(screen.getByText('Total Archives')).toBeInTheDocument()
    expect(screen.getByText('Total Archive Size')).toBeInTheDocument()
    expect(screen.getByText('Compressed Archive Size')).toBeInTheDocument()
    expect(screen.getByText('Repository Size')).toBeInTheDocument()
  })

  it('displays correct archives count', () => {
    render(<RepositoryStatsGrid stats={mockStats} archivesCount={42} />)

    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('formats deduplicated size correctly', () => {
    render(<RepositoryStatsGrid stats={mockStats} archivesCount={10} />)

    // 1 GB formatted
    expect(screen.getByText('1.00 GB')).toBeInTheDocument()
  })

  it('formats original size correctly', () => {
    render(<RepositoryStatsGrid stats={mockStats} archivesCount={10} />)

    expect(screen.getByText('5.00 GB')).toBeInTheDocument()
  })

  it('formats compressed size correctly', () => {
    render(<RepositoryStatsGrid stats={mockStats} archivesCount={10} />)

    expect(screen.getByText('2.00 GB')).toBeInTheDocument()
  })

  it('handles zero values gracefully', () => {
    const zeroStats = {
      original_size: 0,
      compressed_size: 0,
      deduplicated_size: 0,
    }

    render(<RepositoryStatsGrid stats={zeroStats} archivesCount={0} />)

    expect(screen.getAllByText('0 B')).toHaveLength(3)
  })

  it('displays correct units for different sizes', () => {
    const smallStats = {
      original_size: 5120, // 5 KB
      compressed_size: 2048, // 2 KB
      deduplicated_size: 1024, // 1 KB
    }

    render(<RepositoryStatsGrid stats={smallStats} archivesCount={1} />)

    expect(screen.getByText('1.00 KB')).toBeInTheDocument()
  })

  it('shows number of files instead of compressed size for Borg 2', () => {
    render(
      <RepositoryStatsGrid
        stats={{ ...mockStats, total_files: 16 }}
        archivesCount={10}
        borgVersion={2}
      />
    )

    expect(screen.getByText('Number of Files')).toBeInTheDocument()
    expect(screen.getByText('16')).toBeInTheDocument()
  })
})
