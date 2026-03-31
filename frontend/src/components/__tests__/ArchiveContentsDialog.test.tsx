import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse } from 'axios'
import ArchiveContentsDialog from '../ArchiveContentsDialog'

// Mock BorgApiClient so tests don't make real HTTP calls
vi.mock('../../services/borgApi/client', () => ({
  BorgApiClient: vi.fn().mockImplementation(() => ({
    getArchiveContents: vi.fn(),
  })),
}))

import { BorgApiClient } from '../../services/borgApi/client'

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

  const mockRepository = { id: 1, name: 'Test Repo', path: '/test', borg_version: 1 }

  const mockHandlers = {
    onClose: vi.fn(),
    onDownloadFile: vi.fn(),
  }

  let mockGetArchiveContents: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    mockGetArchiveContents = vi.fn()
    vi.mocked(BorgApiClient).mockImplementation(
      () =>
        ({
          getArchiveContents: mockGetArchiveContents,
        }) as any
    )
  })

  it('renders nothing when closed', () => {
    const { container } = renderWithProviders(
      <ArchiveContentsDialog
        open={false}
        archive={mockArchive}
        repository={mockRepository}
        {...mockHandlers}
      />
    )

    expect(container.querySelector('[role="dialog"]')).not.toBeInTheDocument()
  })

  it('renders dialog when open', () => {
    mockGetArchiveContents.mockResolvedValue({
      data: { items: [] },
    } as AxiosResponse)

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repository={mockRepository}
        {...mockHandlers}
      />
    )

    expect(screen.getByText('Archive Contents')).toBeInTheDocument()
    expect(screen.getByText('backup-2024-01-15')).toBeInTheDocument()
  })

  it('shows loading state', () => {
    mockGetArchiveContents.mockImplementation(() => new Promise(() => {}))

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repository={mockRepository}
        {...mockHandlers}
      />
    )

    expect(screen.getByText('Loading archive contents...')).toBeInTheDocument()
  })

  it('displays empty archive message when no items', async () => {
    mockGetArchiveContents.mockResolvedValue({
      data: { items: [] },
    } as AxiosResponse)

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repository={mockRepository}
        {...mockHandlers}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('This archive is empty')).toBeInTheDocument()
    })
  })

  it('displays folders and files', async () => {
    mockGetArchiveContents.mockResolvedValue({
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
        repository={mockRepository}
        {...mockHandlers}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('documents')).toBeInTheDocument()
      expect(screen.getByText('file.txt')).toBeInTheDocument()
    })
  })

  it('navigates into folders when clicked', async () => {
    mockGetArchiveContents.mockResolvedValue({
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
        repository={mockRepository}
        {...mockHandlers}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('documents')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('documents'))

    // Check that client was called with new path
    await waitFor(() => {
      expect(mockGetArchiveContents).toHaveBeenCalledWith(mockArchive.name, 'documents')
    })
  })

  it('displays breadcrumb navigation', async () => {
    mockGetArchiveContents.mockResolvedValue({
      data: { items: [] },
    } as AxiosResponse)

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repository={mockRepository}
        {...mockHandlers}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Root')).toBeInTheDocument()
    })
  })

  it('calls onDownloadFile when download button is clicked', async () => {
    mockGetArchiveContents.mockResolvedValue({
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
        repository={mockRepository}
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
    mockGetArchiveContents.mockResolvedValue({
      data: { items: [] },
    } as AxiosResponse)

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repository={mockRepository}
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
    mockGetArchiveContents.mockResolvedValue({
      data: { items: [] },
    } as AxiosResponse)

    const { rerender } = renderWithProviders(
      <ArchiveContentsDialog
        open={false}
        archive={mockArchive}
        repository={mockRepository}
        {...mockHandlers}
      />
    )

    // Open dialog
    rerender(
      <QueryClientProvider client={createTestQueryClient()}>
        <ArchiveContentsDialog
          open={true}
          archive={mockArchive}
          repository={mockRepository}
          {...mockHandlers}
        />
      </QueryClientProvider>
    )

    // Verify it starts at root path
    await waitFor(() => {
      expect(mockGetArchiveContents).toHaveBeenCalledWith(mockArchive.name, '')
    })
  })

  it('does not show download button when onDownloadFile is not provided', async () => {
    mockGetArchiveContents.mockResolvedValue({
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
        repository={mockRepository}
        onClose={mockHandlers.onClose}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('file.txt')).toBeInTheDocument()
    })

    expect(screen.queryByTitle('Download file')).not.toBeInTheDocument()
  })
})
