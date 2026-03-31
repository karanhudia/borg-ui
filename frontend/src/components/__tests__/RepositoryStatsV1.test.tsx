import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import RepositoryStatsV1 from '../RepositoryStatsV1'

const baseStats = {
  total_size: 10 * 1024 * 1024 * 1024, // 10 GB
  unique_csize: 4 * 1024 * 1024 * 1024, // 4 GB
  unique_size: 6 * 1024 * 1024 * 1024, // 6 GB
  total_chunks: 12500,
  total_unique_chunks: 8200,
}

describe('RepositoryStatsV1', () => {
  it('renders total size', () => {
    renderWithProviders(<RepositoryStatsV1 stats={baseStats} />)
    expect(screen.getByText('10.00 GB')).toBeInTheDocument()
  })

  it('renders used on disk (unique_csize)', () => {
    renderWithProviders(<RepositoryStatsV1 stats={baseStats} />)
    expect(screen.getByText('4.00 GB')).toBeInTheDocument()
  })

  it('renders unique data (unique_size)', () => {
    renderWithProviders(<RepositoryStatsV1 stats={baseStats} />)
    expect(screen.getByText('6.00 GB')).toBeInTheDocument()
  })

  it('renders total chunk count', () => {
    renderWithProviders(<RepositoryStatsV1 stats={baseStats} />)
    expect(screen.getByText('12,500')).toBeInTheDocument()
  })

  it('renders unique chunk count', () => {
    renderWithProviders(<RepositoryStatsV1 stats={baseStats} />)
    expect(screen.getByText('8,200')).toBeInTheDocument()
  })

  it('renders zero bytes gracefully when stats are empty', () => {
    renderWithProviders(<RepositoryStatsV1 stats={{}} />)
    // Should render 0 values without crashing
    expect(screen.getAllByText('0 B').length).toBeGreaterThanOrEqual(1)
  })
})
