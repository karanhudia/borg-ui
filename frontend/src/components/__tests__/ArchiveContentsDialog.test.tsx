import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse } from 'axios'
import ArchiveContentsDialog from '../ArchiveContentsDialog'
import * as browseAPI from '../../services/api'

// Mock the API
vi.mock('../../services/api', () => ({
  browseAPI: {
    getContents: vi.fn(),
  },
  archivesAPI: {},
  repositoriesAPI: {},
  mountsAPI: {},
  restoreAPI: {},
}))

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = createTestQueryClient()
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('ArchiveContentsDialog', () => {
  const mockArchive = {
    id: '1',
    name: 'backup-2024-01-15',
    archive: 'backup-2024-01-15',
    start: '2024-01-15T10:00:00Z',
    time: '2024-01-15T10:00:00Z',
  }

  const mockRepositoryId = 1

  const mockHandlers = {
    onClose: vi.fn(),
    onDownloadFile: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when closed', () => {
    const { container } = renderWithProviders(
      <ArchiveContentsDialog
        open={false}
        archive={mockArchive}
        repositoryId={mockRepositoryId}
        {...mockHandlers}
      />
    )

    expect(container.querySelector('[role="dialog"]')).not.toBeInTheDocument()
  })

  it('renders dialog when open', () => {
    vi.mocked(browseAPI.browseAPI.getContents).mockResolvedValue({
      data: { items: [] },
    } as AxiosResponse)

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repositoryId={mockRepositoryId}
        {...mockHandlers}
      />
    )

    expect(screen.getByText('Archive Contents')).toBeInTheDocument()
    expect(screen.getByText('backup-2024-01-15')).toBeInTheDocument()
  })

  it('shows loading state', () => {
    vi.mocked(browseAPI.browseAPI.getContents).mockImplementation(() => new Promise(() => {}))

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repositoryId={mockRepositoryId}
        {...mockHandlers}
      />
    )

    expect(screen.getByText('Loading archive contents...')).toBeInTheDocument()
  })

  it('displays empty archive message when no items', async () => {
    vi.mocked(browseAPI.browseAPI.getContents).mockResolvedValue({
      data: { items: [] },
    } as AxiosResponse)

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repositoryId={mockRepositoryId}
        {...mockHandlers}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('This archive is empty')).toBeInTheDocument()
    })
  })

  it('displays folders and files', async () => {
    vi.mocked(browseAPI.browseAPI.getContents).mockResolvedValue({
      data: {
        items: [
          {
            name: 'documents',
            path: '/documents',
            type: 'directory',
            size: 1024,
          },
          {
            name: 'file.txt',
            path: '/file.txt',
            type: 'file',
            size: 512,
            mtime: '2024-01-15T10:00:00Z',
          },
        ],
      },
    } as AxiosResponse)

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repositoryId={mockRepositoryId}
        {...mockHandlers}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('documents')).toBeInTheDocument()
      expect(screen.getByText('file.txt')).toBeInTheDocument()
    })
  })

  it('navigates into folders when clicked', async () => {
    vi.mocked(browseAPI.browseAPI.getContents).mockResolvedValue({
      data: {
        items: [
          {
            name: 'documents',
            path: '/documents',
            type: 'directory',
            size: 1024,
          },
        ],
      },
    } as AxiosResponse)

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repositoryId={mockRepositoryId}
        {...mockHandlers}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('documents')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('documents'))

    // Check that API was called with new path
    await waitFor(() => {
      expect(browseAPI.browseAPI.getContents).toHaveBeenCalledWith(
        mockRepositoryId,
        mockArchive.name,
        'documents'
      )
    })
  })

  it('displays breadcrumb navigation', async () => {
    vi.mocked(browseAPI.browseAPI.getContents).mockResolvedValue({
      data: { items: [] },
    } as AxiosResponse)

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repositoryId={mockRepositoryId}
        {...mockHandlers}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Root')).toBeInTheDocument()
    })
  })

  it('calls onDownloadFile when download button is clicked', async () => {
    vi.mocked(browseAPI.browseAPI.getContents).mockResolvedValue({
      data: {
        items: [
          {
            name: 'file.txt',
            path: '/file.txt',
            type: 'file',
            size: 512,
            mtime: '2024-01-15T10:00:00Z',
          },
        ],
      },
    } as AxiosResponse)

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repositoryId={mockRepositoryId}
        {...mockHandlers}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('file.txt')).toBeInTheDocument()
    })

    const downloadButton = screen.getByTitle('Download file')
    fireEvent.click(downloadButton)

    expect(mockHandlers.onDownloadFile).toHaveBeenCalledWith(mockArchive.name, '/file.txt')
  })

  it('calls onClose when Close button is clicked', async () => {
    vi.mocked(browseAPI.browseAPI.getContents).mockResolvedValue({
      data: { items: [] },
    } as AxiosResponse)

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repositoryId={mockRepositoryId}
        {...mockHandlers}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Archive Contents')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(mockHandlers.onClose).toHaveBeenCalledTimes(1)
  })

  it('resets path when dialog opens with new archive', async () => {
    vi.mocked(browseAPI.browseAPI.getContents).mockResolvedValue({
      data: { items: [] },
    } as AxiosResponse)

    const { rerender } = renderWithProviders(
      <ArchiveContentsDialog
        open={false}
        archive={mockArchive}
        repositoryId={mockRepositoryId}
        {...mockHandlers}
      />
    )

    // Open dialog
    rerender(
      <QueryClientProvider client={createTestQueryClient()}>
        <ArchiveContentsDialog
          open={true}
          archive={mockArchive}
          repositoryId={mockRepositoryId}
          {...mockHandlers}
        />
      </QueryClientProvider>
    )

    // Verify it starts at root path
    await waitFor(() => {
      expect(browseAPI.browseAPI.getContents).toHaveBeenCalledWith(
        mockRepositoryId,
        mockArchive.name,
        ''
      )
    })
  })

  it('does not show download button when onDownloadFile is not provided', async () => {
    vi.mocked(browseAPI.browseAPI.getContents).mockResolvedValue({
      data: {
        items: [
          {
            name: 'file.txt',
            path: '/file.txt',
            type: 'file',
            size: 512,
            mtime: '2024-01-15T10:00:00Z',
          },
        ],
      },
    } as AxiosResponse)

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repositoryId={mockRepositoryId}
        onClose={mockHandlers.onClose}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('file.txt')).toBeInTheDocument()
    })

    expect(screen.queryByTitle('Download file')).not.toBeInTheDocument()
  })
})
