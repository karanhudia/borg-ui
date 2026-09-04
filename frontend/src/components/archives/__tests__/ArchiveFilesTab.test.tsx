import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import ArchiveFilesTab from '../ArchiveFilesTab'
import type { ArchiveDetailResponse } from '../../../types/archives'
import type { Repository } from '@/types'
import type { ArchivePathSelectionData } from '../../ArchivePathSelector'

vi.mock('../../../hooks/usePlan', () => ({
  usePlan: () => ({
    plan: 'community',
    isLoading: false,
    isPro: false,
    isFree: true,
    can: () => true,
  }),
}))

vi.mock('../../../services/api', () => ({
  archivesAPI: {
    getPathHistory: vi.fn(),
    listStored: vi.fn(),
  },
}))

vi.mock('../../ArchivePathSelector', () => ({
  default: ({
    data,
    onChange,
  }: {
    data: ArchivePathSelectionData
    onChange: (data: Partial<ArchivePathSelectionData>) => void
  }) => (
    <button
      data-testid="archive-path-selector"
      onClick={() =>
        onChange({
          selectedPaths: [...data.selectedPaths, 'home/karan/docs/invoices.xlsx'],
          selectedItems: [
            ...(data.selectedItems || []),
            { path: 'home/karan/docs/invoices.xlsx', type: 'file' },
          ],
        })
      }
    />
  ),
}))

const archive: ArchiveDetailResponse = {
  id: 12,
  repository_id: 7,
  borg_id: 'abc123',
  name: 'nas-2026-09-02T02:00',
  series: 'nightly',
  start: '2026-09-02T02:00:00Z',
  end: '2026-09-02T02:14:00Z',
  duration_seconds: 840,
  nfiles: 12000,
  original_size: 90_000_000_000,
  compressed_size: 60_000_000_000,
  deduplicated_size: 41_200_000_000,
  hostname: 'nas',
  username: 'root',
  comment: null,
  backup_operation_id: 55,
  history_state: 'indexed',
  history_indexed_at: '2026-09-02T02:20:00Z',
  history_rows: 40,
  history_truncated: false,
  first_seen_at: '2026-09-02T02:00:00Z',
  last_seen_at: '2026-09-02T02:00:00Z',
  predecessor_id: 11,
  successor_id: null,
  history_available: true,
}

const repository = { id: 7, name: 'nas', path: '/data/nas', mode: 'full' } as Repository

describe('ArchiveFilesTab', () => {
  it('shows no footer when there is no selection', () => {
    renderWithProviders(
      <ArchiveFilesTab repositoryId={7} repository={repository} archive={archive} />
    )
    expect(screen.queryByText(/selected/i)).not.toBeInTheDocument()
  })

  it('renders the path selector and details pane', () => {
    renderWithProviders(
      <ArchiveFilesTab repositoryId={7} repository={repository} archive={archive} />
    )
    expect(screen.getByTestId('archive-path-selector')).toBeInTheDocument()
    expect(screen.getByText(/folder/i)).toBeInTheDocument()
  })

  it('shows the footer with the selection count once a file is selected', () => {
    renderWithProviders(
      <ArchiveFilesTab repositoryId={7} repository={repository} archive={archive} />
    )
    fireEvent.click(screen.getByTestId('archive-path-selector'))
    expect(screen.getByText(/1 selected/i)).toBeInTheDocument()
  })
})
