import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import RepositoryStatsGrid from '../RepositoryStatsGrid'

describe('RepositoryStatsGrid', () => {
  const mockStats = {
    unique_csize: 1073741824, // 1 GB
    unique_size: 2147483648, // 2 GB
    total_size: 5368709120, // 5 GB
  }

  it('renders all stat cards', () => {
    render(<RepositoryStatsGrid stats={mockStats} archivesCount={10} />)

    expect(screen.getByText('Total Archives')).toBeInTheDocument()
    expect(screen.getByText('Space Used')).toBeInTheDocument()
    expect(screen.getByText('Space Saved')).toBeInTheDocument()
    expect(screen.getByText('Compression')).toBeInTheDocument()
    expect(screen.getByText('Deduplication')).toBeInTheDocument()
  })

  it('displays correct archives count', () => {
    render(<RepositoryStatsGrid stats={mockStats} archivesCount={42} />)

    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('formats space used correctly', () => {
    render(<RepositoryStatsGrid stats={mockStats} archivesCount={10} />)

    // 1 GB formatted
    expect(screen.getByText('1.00 GB')).toBeInTheDocument()
  })

  it('calculates space saved correctly', () => {
    render(<RepositoryStatsGrid stats={mockStats} archivesCount={10} />)

    // 5 GB - 1 GB = 4 GB
    expect(screen.getByText('4.00 GB')).toBeInTheDocument()
  })

  it('calculates compression ratio correctly', () => {
    render(<RepositoryStatsGrid stats={mockStats} archivesCount={10} />)

    // (1 - 1GB/2GB) * 100 = 50.0%
    expect(screen.getByText('50.0%')).toBeInTheDocument()
  })

  it('calculates deduplication ratio correctly', () => {
    render(<RepositoryStatsGrid stats={mockStats} archivesCount={10} />)

    // (1 - 2GB/5GB) * 100 = 60.0%
    expect(screen.getByText('60.0%')).toBeInTheDocument()
  })

  it('handles zero values gracefully', () => {
    const zeroStats = {
      unique_csize: 0,
      unique_size: 0,
      total_size: 0,
    }

    render(<RepositoryStatsGrid stats={zeroStats} archivesCount={0} />)

    expect(screen.getAllByText('0 B')).toHaveLength(2) // Space used and space saved
    expect(screen.getAllByText('0%')).toHaveLength(2) // Compression and Deduplication (when zero, no decimal)
  })

  it('handles no space saved scenario', () => {
    const noSavingsStats = {
      unique_csize: 1000000,
      unique_size: 1000000,
      total_size: 1000000,
    }

    render(<RepositoryStatsGrid stats={noSavingsStats} archivesCount={5} />)

    expect(screen.getByText('0 B')).toBeInTheDocument() // Space Saved
  })

  it('displays correct units for different sizes', () => {
    const smallStats = {
      unique_csize: 1024, // 1 KB
      unique_size: 2048, // 2 KB
      total_size: 5120, // 5 KB
    }

    render(<RepositoryStatsGrid stats={smallStats} archivesCount={1} />)

    expect(screen.getByText('1.00 KB')).toBeInTheDocument()
  })
})
