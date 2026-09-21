import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, within, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import ArchiveSearchField from '../ArchiveSearchField'
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
    search: vi.fn(),
    getPathHistory: vi.fn(),
    listStored: vi.fn(),
  },
}))

const newestBySeries = { nightly: 12, photos: 40 }
const onRestorePath = vi.fn()

function renderField() {
  renderWithProviders(
    <ArchiveSearchField
      repositoryId={7}
      newestArchiveIdBySeries={newestBySeries}
      onRestorePath={onRestorePath}
    />
  )
}

function searchResult(overrides: Record<string, unknown> = {}) {
  return {
    path: 'home/alex/docs/invoices.xlsx',
    first_seen_archive_id: 3,
    first_seen: '2026-08-24T02:00:00Z',
    last_seen_archive_id: 12,
    last_seen: '2026-09-02T02:00:00Z',
    archive_count: 7,
    series: 'nightly',
    last_change: 'modified',
    ...overrides,
  }
}

function respondWith(results: ReturnType<typeof searchResult>[], truncated = false) {
  vi.mocked(archivesAPI.search).mockResolvedValue({
    data: { query: 'invoices', results, truncated },
  } as never)
}

function submitSearch(value = 'invoices') {
  fireEvent.change(screen.getByRole('textbox'), { target: { value } })
  fireEvent.submit(screen.getByRole('search'))
}

describe('ArchiveSearchField', () => {
  beforeEach(() => {
    mockPlanCan.mockReturnValue(true)
    onRestorePath.mockReset()
    vi.mocked(archivesAPI.search).mockReset()
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: { path: 'x', entries: [], present: [], coverage: null },
    } as never)
    vi.mocked(archivesAPI.listStored).mockResolvedValue({ data: { archives: [] } } as never)
  })

  it('opens a dialog listing matches with their last seen archive', async () => {
    respondWith([searchResult()])
    renderField()
    submitSearch()
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    const row = await screen.findByTestId('search-result-home/alex/docs/invoices.xlsx')
    expect(within(row).getByText('invoices.xlsx')).toBeInTheDocument()
    expect(within(row).getByText(/in 7 archives/)).toBeInTheDocument()
  })

  it("reads present against the newest archive of the result's own series", async () => {
    // The photos series runs later in the day, so it owns the newest archive
    // in the repository. A file at the head of the nightly series is still
    // present, and comparing against the repository-wide newest id would
    // report it as gone.
    respondWith([
      searchResult(),
      searchResult({
        path: 'home/alex/photos/old.heic',
        series: 'photos',
        last_seen_archive_id: 31,
      }),
    ])
    renderField()
    submitSearch()
    const present = await screen.findByTestId('search-result-home/alex/docs/invoices.xlsx')
    const absent = screen.getByTestId('search-result-home/alex/photos/old.heic')
    expect(within(present).getByText('In latest')).toBeInTheDocument()
    expect(within(absent).getByText('Not in latest')).toBeInTheDocument()
  })

  it('searches again from inside the dialog without closing it', async () => {
    respondWith([searchResult()])
    renderField()
    submitSearch()
    const dialog = await screen.findByRole('dialog')

    respondWith([searchResult({ path: 'home/alex/docs/taxes.pdf' })])
    fireEvent.change(within(dialog).getByPlaceholderText(/search files/i), {
      target: { value: 'taxes' },
    })

    expect(await screen.findByTestId('search-result-home/alex/docs/taxes.pdf')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await waitFor(() => expect(archivesAPI.search).toHaveBeenLastCalledWith(7, 'taxes'))
  })

  it('shows the history of the file that is picked', async () => {
    respondWith([searchResult()])
    renderField()
    submitSearch()
    expect(screen.queryByText('home/alex/docs/invoices.xlsx')).not.toBeInTheDocument()

    fireEvent.click(await screen.findByTestId('search-result-home/alex/docs/invoices.xlsx'))

    // The detail pane names the full path and asks the history route for it.
    expect(await screen.findByText('home/alex/docs/invoices.xlsx')).toBeInTheDocument()
    await waitFor(() =>
      expect(archivesAPI.getPathHistory).toHaveBeenCalledWith(7, 'home/alex/docs/invoices.xlsx')
    )
  })

  it('hands a restore back to the page with the archive that holds the version', async () => {
    // Sending the reader to the archive page would land them at its root with
    // the file nowhere in sight, so the page opens the restore wizard on the
    // archive of the version they picked, with the path selected.
    respondWith([searchResult()])
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'home/alex/docs/invoices.xlsx',
        entries: [
          {
            archive_id: 9,
            archive_name: 'nightly-2026-09-01',
            series: 'nightly',
            start: '2026-09-01T02:00:00Z',
            change: 'modified',
            size_before: 10,
            size_after: 20,
          },
        ],
        present: [],
        coverage: { indexed: 1, total: 1, exhausted: 0, capability: 'available' },
      },
    } as never)

    renderField()
    submitSearch()
    fireEvent.click(await screen.findByTestId('search-result-home/alex/docs/invoices.xlsx'))
    fireEvent.click(await screen.findByRole('button', { name: /restore this/i }))

    expect(onRestorePath).toHaveBeenCalledWith(9, 'home/alex/docs/invoices.xlsx')
    // The dialog closes so the wizard is not stacked behind it.
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('disables the field on a plan without the history feature', () => {
    mockPlanCan.mockReturnValue(false)
    renderField()
    expect(screen.getByRole('textbox')).toBeDisabled()
  })
})
