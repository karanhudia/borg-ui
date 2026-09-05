import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
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
  },
}))

function renderField() {
  renderWithProviders(<ArchiveSearchField repositoryId={7} newestArchiveId={12} />)
}

describe('ArchiveSearchField', () => {
  beforeEach(() => {
    mockPlanCan.mockReturnValue(true)
    vi.mocked(archivesAPI.search).mockReset()
  })

  it('opens a dialog listing matches with their last seen archive', async () => {
    vi.mocked(archivesAPI.search).mockResolvedValue({
      data: {
        query: 'invoices',
        results: [
          {
            path: 'home/karan/docs/invoices.xlsx',
            first_seen_archive_id: 3,
            first_seen: '2026-08-24T02:00:00Z',
            last_seen_archive_id: 12,
            last_seen: '2026-09-02T02:00:00Z',
            archive_count: 7,
            series: 'nightly',
            last_change: 'modified',
          },
        ],
        truncated: false,
      },
    } as never)

    renderField()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'invoices' } })
    fireEvent.submit(screen.getByRole('search'))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(await screen.findByText('home/karan/docs/invoices.xlsx')).toBeInTheDocument()
  })

  it('disables the field on a plan without the history feature', () => {
    mockPlanCan.mockReturnValue(false)
    renderField()
    expect(screen.getByRole('textbox')).toBeDisabled()
  })
})
