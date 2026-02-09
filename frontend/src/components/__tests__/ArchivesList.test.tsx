import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ArchivesList from '../ArchivesList'

// Mock ArchiveCard since it's tested separately
vi.mock('../ArchiveCard', () => ({
  default: ({ archive }: { archive: any }) => (
    <div data-testid={`archive-card-${archive.id}`}>Archive: {archive.name}</div>
  ),
}))

describe('ArchivesList', () => {
  const mockArchives = [
    {
      id: '1',
      name: 'backup-2024-01-15',
      archive: 'backup-2024-01-15',
      start: '2024-01-15T10:00:00Z',
      time: '2024-01-15T10:00:00Z',
    },
    {
      id: '2',
      name: 'backup-2024-01-16',
      archive: 'backup-2024-01-16',
      start: '2024-01-16T10:00:00Z',
      time: '2024-01-16T10:00:00Z',
    },
    {
      id: '3',
      name: 'backup-2024-01-17',
      archive: 'backup-2024-01-17',
      start: '2024-01-17T10:00:00Z',
      time: '2024-01-17T10:00:00Z',
    },
  ]

  const mockHandlers = {
    onViewArchive: vi.fn(),
    onRestoreArchive: vi.fn(),
    onMountArchive: vi.fn(),
    onDeleteArchive: vi.fn(),
  }

  it('renders loading state', () => {
    render(
      <ArchivesList archives={[]} repositoryName="Test Repo" loading={true} {...mockHandlers} />
    )

    expect(screen.getByText('Loading archives...')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('renders empty state when no archives', () => {
    render(
      <ArchivesList archives={[]} repositoryName="Test Repo" loading={false} {...mockHandlers} />
    )

    expect(screen.getByText('No archives found in this repository')).toBeInTheDocument()
  })

  it('renders header with repository name and count', () => {
    render(
      <ArchivesList
        archives={mockArchives}
        repositoryName="My Backup Repo"
        loading={false}
        {...mockHandlers}
      />
    )

    expect(screen.getByText('Archives for My Backup Repo')).toBeInTheDocument()
    expect(screen.getByText('3 archives')).toBeInTheDocument()
  })

  it('uses singular "archive" for count of 1', () => {
    render(
      <ArchivesList
        archives={[mockArchives[0]]}
        repositoryName="Test Repo"
        loading={false}
        {...mockHandlers}
      />
    )

    expect(screen.getByText('1 archive')).toBeInTheDocument()
  })

  it('renders all archives as cards', () => {
    render(
      <ArchivesList
        archives={mockArchives}
        repositoryName="Test Repo"
        loading={false}
        {...mockHandlers}
      />
    )

    expect(screen.getByTestId('archive-card-1')).toBeInTheDocument()
    expect(screen.getByTestId('archive-card-2')).toBeInTheDocument()
    expect(screen.getByTestId('archive-card-3')).toBeInTheDocument()

    expect(screen.getByText('Archive: backup-2024-01-15')).toBeInTheDocument()
    expect(screen.getByText('Archive: backup-2024-01-16')).toBeInTheDocument()
    expect(screen.getByText('Archive: backup-2024-01-17')).toBeInTheDocument()
  })

  it('does not render header in loading state', () => {
    render(
      <ArchivesList
        archives={mockArchives}
        repositoryName="Test Repo"
        loading={true}
        {...mockHandlers}
      />
    )

    expect(screen.queryByText('Archives for Test Repo')).not.toBeInTheDocument()
  })

  it('does not render header in empty state', () => {
    render(
      <ArchivesList archives={[]} repositoryName="Test Repo" loading={false} {...mockHandlers} />
    )

    expect(screen.queryByText('Archives for Test Repo')).not.toBeInTheDocument()
  })

  it('handles large number of archives', () => {
    const manyArchives = Array.from({ length: 100 }, (_, i) => ({
      id: `${i}`,
      name: `backup-${i}`,
      archive: `backup-${i}`,
      start: '2024-01-15T10:00:00Z',
      time: '2024-01-15T10:00:00Z',
    }))

    render(
      <ArchivesList
        archives={manyArchives}
        repositoryName="Test Repo"
        loading={false}
        {...mockHandlers}
      />
    )

    expect(screen.getByText('100 archives')).toBeInTheDocument()
    // With pagination (default 10 per page), only first 10 should be visible
    expect(screen.getByTestId('archive-card-0')).toBeInTheDocument()
    expect(screen.getByTestId('archive-card-9')).toBeInTheDocument()
    expect(screen.queryByTestId('archive-card-10')).not.toBeInTheDocument()
    expect(screen.queryByTestId('archive-card-99')).not.toBeInTheDocument()
  })

  describe('Pagination', () => {
    const createArchives = (count: number) =>
      Array.from({ length: count }, (_, i) => ({
        id: `${i}`,
        name: `backup-${i}`,
        archive: `backup-${i}`,
        start: '2024-01-15T10:00:00Z',
        time: '2024-01-15T10:00:00Z',
      }))

    it('renders pagination controls when archives exist', () => {
      const archives = createArchives(15)
      render(
        <ArchivesList
          archives={archives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      expect(screen.getByText('Archives per page:')).toBeInTheDocument()
      expect(screen.getByText(/1–10 of 15/)).toBeInTheDocument()
    })

    it('does not render pagination for empty archives', () => {
      render(
        <ArchivesList archives={[]} repositoryName="Test Repo" loading={false} {...mockHandlers} />
      )

      expect(screen.queryByText('Archives per page:')).not.toBeInTheDocument()
    })

    it('displays correct number of archives per page', () => {
      const archives = createArchives(25)
      render(
        <ArchivesList
          archives={archives}
          repositoryName="Test Repo"
          loading={false}
          defaultRowsPerPage={10}
          {...mockHandlers}
        />
      )

      // First 10 should be visible
      expect(screen.getByTestId('archive-card-0')).toBeInTheDocument()
      expect(screen.getByTestId('archive-card-9')).toBeInTheDocument()
      // 11th should not be visible
      expect(screen.queryByTestId('archive-card-10')).not.toBeInTheDocument()
    })

    it('shows correct pagination text', () => {
      const archives = createArchives(35)
      render(
        <ArchivesList
          archives={archives}
          repositoryName="Test Repo"
          loading={false}
          defaultRowsPerPage={10}
          {...mockHandlers}
        />
      )

      expect(screen.getByText(/1–10 of 35/)).toBeInTheDocument()
    })

    it('handles custom rows per page options', () => {
      const archives = createArchives(50)
      render(
        <ArchivesList
          archives={archives}
          repositoryName="Test Repo"
          loading={false}
          defaultRowsPerPage={25}
          rowsPerPageOptions={[10, 25, 50]}
          {...mockHandlers}
        />
      )

      expect(screen.getByText(/1–25 of 50/)).toBeInTheDocument()
    })

    it('renders all archives on single page when count is less than page size', () => {
      const archives = createArchives(5)
      render(
        <ArchivesList
          archives={archives}
          repositoryName="Test Repo"
          loading={false}
          defaultRowsPerPage={10}
          {...mockHandlers}
        />
      )

      // All 5 should be visible
      expect(screen.getByTestId('archive-card-0')).toBeInTheDocument()
      expect(screen.getByTestId('archive-card-4')).toBeInTheDocument()
      expect(screen.getByText(/1–5 of 5/)).toBeInTheDocument()
    })
  })
})
