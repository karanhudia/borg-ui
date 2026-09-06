import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import FileHistoryPanel from '../FileHistoryPanel'
import { archivesAPI } from '../../../services/api'

const mockPlanCan = vi.fn(() => true)

vi.mock('../../../hooks/usePlan', () => ({
  usePlan: () => ({
    plan: 'community',
    isLoading: false,
    isPro: false,
    isFree: true,
    can: mockPlanCan,
  }),
}))

vi.mock('../../../services/api', () => ({
  archivesAPI: {
    getPathHistory: vi.fn(),
    listStored: vi.fn(),
  },
}))

function renderPanel(path = 'home/karan/docs/invoices.xlsx') {
  const onRestore = vi.fn()
  renderWithProviders(<FileHistoryPanel repositoryId={7} path={path} onRestoreEntry={onRestore} />)
  return { onRestore }
}

describe('FileHistoryPanel', () => {
  beforeEach(() => {
    mockPlanCan.mockReturnValue(true)
    vi.mocked(archivesAPI.getPathHistory).mockReset()
    vi.mocked(archivesAPI.listStored).mockReset()
    vi.mocked(archivesAPI.listStored).mockResolvedValue({
      data: {
        archives: [],
        series: [],
        sync_state: 'fresh',
        last_synced_at: null,
        history_available: true,
      },
    } as never)
  })

  it('renders one row per history entry with its size and change', async () => {
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'home/karan/docs/invoices.xlsx',
        entries: [
          {
            archive_id: 12,
            archive_name: 'nas-2026-09-02T02:00',
            series: 'nightly',
            start: '2026-09-02T02:00:00Z',
            change: 'modified',
            size_before: 374_000,
            size_after: 412_000,
            mode_changed: false,
            owner_changed: false,
          },
          {
            archive_id: 3,
            archive_name: 'nas-2026-08-24T02:00',
            series: 'nightly',
            start: '2026-08-24T02:00:00Z',
            change: 'added',
            size_before: null,
            size_after: 374_000,
            mode_changed: false,
            owner_changed: false,
          },
        ],
        present: [{ series: 'nightly', from_archive_id: 3, to_archive_id: null }],
        present_in_latest: true,
      },
    } as never)

    renderPanel()
    expect(await screen.findByText('nas-2026-09-02T02:00')).toBeInTheDocument()
    expect(screen.getByText('nas-2026-08-24T02:00')).toBeInTheDocument()
    expect(screen.getByText(/first seen/i)).toBeInTheDocument()
  })

  it('renders a not-present range from the present ranges', async () => {
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'home/karan/docs/invoices.xlsx',
        entries: [
          {
            archive_id: 12,
            archive_name: 'nas-2026-09-02T02:00',
            series: 'nightly',
            start: '2026-09-02T02:00:00Z',
            change: 'added',
            size_before: null,
            size_after: 374_000,
            mode_changed: false,
            owner_changed: false,
          },
        ],
        present: [{ series: 'nightly', from_archive_id: 12, to_archive_id: null }],
        present_in_latest: true,
      },
    } as never)
    vi.mocked(archivesAPI.listStored).mockResolvedValue({
      data: {
        archives: [
          { id: 9, name: 'a9', series: 'nightly', start: '2026-08-30T02:00:00Z' },
          { id: 10, name: 'a10', series: 'nightly', start: '2026-08-31T02:00:00Z' },
          { id: 11, name: 'a11', series: 'nightly', start: '2026-09-01T02:00:00Z' },
          {
            id: 12,
            name: 'nas-2026-09-02T02:00',
            series: 'nightly',
            start: '2026-09-02T02:00:00Z',
          },
        ],
        series: ['nightly'],
        sync_state: 'fresh',
        last_synced_at: null,
        history_available: true,
      },
    } as never)

    renderPanel()
    expect(await screen.findByText(/not present in 3 older archives/i)).toBeInTheDocument()
  })

  it('renders a restore action per entry', async () => {
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'home/karan/docs/invoices.xlsx',
        entries: [
          {
            archive_id: 12,
            archive_name: 'nas-2026-09-02T02:00',
            series: 'nightly',
            start: '2026-09-02T02:00:00Z',
            change: 'modified',
            size_before: 374_000,
            size_after: 412_000,
            mode_changed: false,
            owner_changed: false,
          },
        ],
        present: [],
        present_in_latest: true,
      },
    } as never)

    const { onRestore } = renderPanel()
    const button = await screen.findByRole('button', { name: /restore this/i })
    fireEvent.click(button)
    expect(onRestore).toHaveBeenCalledWith(expect.objectContaining({ archive_id: 12 }))
  })

  it('renders disabled when the plan lacks the feature', () => {
    mockPlanCan.mockReturnValue(false)
    renderPanel()
    expect(screen.queryByRole('button', { name: /restore this/i })).not.toBeInTheDocument()
  })
})
