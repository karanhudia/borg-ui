import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import RepositoryStatsV2 from '../RepositoryStatsV2'

const archives = [
  { name: 'backup-2024-01-01', time: '2024-01-01T10:00:00Z', stats: { original_size: 2 * 1024 * 1024 * 1024, nfiles: 1500 } },
  { name: 'backup-2024-02-01', time: '2024-02-01T10:00:00Z', stats: { original_size: 3 * 1024 * 1024 * 1024, nfiles: 2000 } },
]

describe('RepositoryStatsV2', () => {
  it('renders empty state when archives array is empty', () => {
    renderWithProviders(<RepositoryStatsV2 archives={[]} />)
    expect(screen.getByText(/no backups yet/i)).toBeInTheDocument()
  })

  it('renders latest backup size from the last archive', () => {
    renderWithProviders(<RepositoryStatsV2 archives={archives} />)
    expect(screen.getByText('3.00 GB')).toBeInTheDocument()
  })

  it('renders file count from the latest archive', () => {
    renderWithProviders(<RepositoryStatsV2 archives={archives} />)
    expect(screen.getByText('2,000')).toBeInTheDocument()
  })

  it('renders total archive count', () => {
    renderWithProviders(<RepositoryStatsV2 archives={archives} />)
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('renders first and latest backup date labels', () => {
    renderWithProviders(<RepositoryStatsV2 archives={archives} />)
    expect(screen.getAllByText(/first backup/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/latest backup/i).length).toBeGreaterThanOrEqual(1)
  })

  it('handles single archive without crashing', () => {
    renderWithProviders(<RepositoryStatsV2 archives={[archives[0]]} />)
    expect(screen.getByText('2.00 GB')).toBeInTheDocument()
    expect(screen.getByText('1,500')).toBeInTheDocument()
  })

  it('shows N/A when archive has no time field', () => {
    renderWithProviders(<RepositoryStatsV2 archives={[{ stats: { original_size: 1024, nfiles: 1 } }]} />)
    expect(screen.getAllByText('N/A').length).toBeGreaterThanOrEqual(1)
  })
})
