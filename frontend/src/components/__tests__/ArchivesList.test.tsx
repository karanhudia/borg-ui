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
    expect(screen.getByTestId('archive-card-0')).toBeInTheDocument()
    expect(screen.getByTestId('archive-card-99')).toBeInTheDocument()
  })
})
