import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse } from 'axios'
import ArchiveContentsDialog from '../ArchiveContentsDialog'

// Mock BorgApiClient so tests don't make real HTTP calls
vi.mock('../../services/borgApi/client', () => ({
  BorgApiClient: vi.fn(function () {
    return { getArchiveContents: vi.fn() }
  }),
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
    vi.mocked(BorgApiClient).mockImplementation(function () {
      return { getArchiveContents: mockGetArchiveContents } as unknown as BorgApiClient
    })
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

  it('shows loading state', async () => {
    mockGetArchiveContents.mockImplementation(() => new Promise(() => {}))

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repository={mockRepository}
        {...mockHandlers}
      />
    )

    await waitFor(() => {
      expect(document.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0)
    })
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

  it('shows Borg UI canary folders as managed archive content', async () => {
    mockGetArchiveContents.mockImplementation((_archiveId, _archiveName, path) => {
      if (path === '') {
        return Promise.resolve({
          data: {
            items: [
              {
                name: '.borg-ui',
                path: '.borg-ui',
                type: 'directory',
                size: 923,
                managed: true,
                managed_type: 'restore_canary',
              },
            ],
          },
        } as AxiosResponse)
      }

      return Promise.resolve({
        data: {
          items: [
            {
              name: 'manifest.json',
              path: '.borg-ui/restore-canaries/repository-1/.borgui-canary/manifest.json',
              type: 'file',
              size: 128,
              managed: true,
              managed_type: 'restore_canary',
            },
          ],
        },
      } as AxiosResponse)
    })

    renderWithProviders(
      <ArchiveContentsDialog
        open={true}
        archive={mockArchive}
        repository={mockRepository}
        {...mockHandlers}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('.borg-ui')).toBeInTheDocument()
      expect(screen.getByText('Borg UI canary')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('.borg-ui'))

    await waitFor(() => {
      expect(screen.getByText('manifest.json')).toBeInTheDocument()
      expect(
        screen.getByText(
          'This folder is managed by Borg UI for canary restore checks. It is safe to leave untouched.'
        )
      ).toBeInTheDocument()
    })
  })

  it('hides folder size when the backend omits it', async () => {
    mockGetArchiveContents.mockResolvedValue({
      data: {
        items: [
          {
            name: 'documents',
            path: '/documents',
            type: 'directory',
            size: null,
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
    expect(screen.queryByText('0 B')).not.toBeInTheDocument()
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
      expect(mockGetArchiveContents).toHaveBeenCalledWith(
        mockArchive.id,
        mockArchive.name,
        'documents'
      )
    })
  })

  it('reuses the same query path when returning via breadcrumb', async () => {
    mockGetArchiveContents.mockImplementation((_archiveId, _archiveName, path) => {
      if (path === '') {
        return Promise.resolve({
          data: {
            items: [
              {
                name: 'documents',
                path: 'documents',
                type: 'directory',
                size: 1024,
              },
            ],
          },
        } as AxiosResponse)
      }

      if (path === 'documents') {
        return Promise.resolve({
          data: {
            items: [
              {
                name: 'notes.txt',
                path: 'documents/notes.txt',
                type: 'file',
                size: 512,
                mtime: '2024-01-15T10:00:00Z',
              },
            ],
          },
        } as AxiosResponse)
      }

      return Promise.resolve({ data: { items: [] } } as AxiosResponse)
    })

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

    await waitFor(() => {
      expect(screen.getByText('notes.txt')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Root'))

    await waitFor(() => {
      expect(screen.getByText('documents')).toBeInTheDocument()
    })

    expect(mockGetArchiveContents.mock.calls.map((call) => call[2])).toEqual(['', 'documents'])
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
      expect(mockGetArchiveContents).toHaveBeenCalledWith(mockArchive.id, mockArchive.name, '')
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
