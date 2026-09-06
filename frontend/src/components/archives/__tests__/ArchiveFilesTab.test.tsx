import { describe, it, expect, vi } from 'vitest'
import { useEffect, useRef } from 'react'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import ArchiveFilesTab from '../ArchiveFilesTab'
import type { ArchiveDetailResponse } from '../../../types/archives'
import type { Repository } from '@/types'
import type { ArchiveBrowseState, ArchivePathSelectionData } from '../../ArchivePathSelector'

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

const browseItems = [
  { name: 'docs', type: 'directory' as const, path: 'home/karan/docs' },
  { name: 'invoices.xlsx', type: 'file' as const, path: 'home/karan/invoices.xlsx', size: 9400 },
]

const focusFilterSpy = vi.fn()
let lastActiveIndex: number | undefined

function MockArchivePathSelector({
  data,
  onChange,
  onBrowseStateChange,
  activeIndex,
}: {
  data: ArchivePathSelectionData
  onChange: (data: Partial<ArchivePathSelectionData>) => void
  onBrowseStateChange?: (state: ArchiveBrowseState) => void
  activeIndex?: number
}) {
  lastActiveIndex = activeIndex
  // The real selector publishes callbacks that read the current selection
  // through refs, so a state published once still toggles against what is
  // selected now. The mock reads `data` at call time for the same reason.
  const dataRef = useRef(data)
  dataRef.current = data
  useEffect(() => {
    onBrowseStateChange?.({
      currentPath: 'home/karan',
      items: browseItems,
      navigateTo: vi.fn(),
      focusFilter: focusFilterSpy,
      activateItem: (item) => {
        if (item.type === 'file') {
          const current = dataRef.current
          onChange({
            selectedPaths: [...current.selectedPaths, item.path],
            selectedItems: [...(current.selectedItems || []), { path: item.path, type: item.type }],
          })
        }
      },
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return (
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
  )
}

vi.mock('../../ArchivePathSelector', () => ({
  default: MockArchivePathSelector,
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
    expect(screen.getByText('Folder')).toBeInTheDocument()
  })

  it('shows the footer with the selection count once a file is selected', () => {
    renderWithProviders(
      <ArchiveFilesTab repositoryId={7} repository={repository} archive={archive} />
    )
    fireEvent.click(screen.getByTestId('archive-path-selector'))
    expect(screen.getByText(/1 selected/i)).toBeInTheDocument()
  })

  describe('keyboard navigation', () => {
    function renderTab() {
      const { container } = renderWithProviders(
        <ArchiveFilesTab repositoryId={7} repository={repository} archive={archive} />
      )
      return container.firstChild as HTMLElement
    }

    it('moves the active row with ArrowDown', () => {
      const root = renderTab()
      fireEvent.keyDown(root, { key: 'ArrowDown' })
      fireEvent.keyDown(root, { key: 'Enter' })
      expect(screen.getByText(/1 selected/i)).toBeInTheDocument()
    })

    it('shows the real size of the selected file in the pane and the footer', () => {
      const root = renderTab()
      fireEvent.keyDown(root, { key: 'ArrowDown' })
      fireEvent.keyDown(root, { key: 'Enter' })
      expect(screen.getAllByText(/9\.18 KB/).length).toBeGreaterThanOrEqual(2)
      expect(screen.getByText('1 selected (9.18 KB)')).toBeInTheDocument()
    })

    it('opens restore from the footer for the whole selection', () => {
      const onRestorePaths = vi.fn()
      renderWithProviders(
        <ArchiveFilesTab
          repositoryId={7}
          repository={repository}
          archive={archive}
          onRestorePaths={onRestorePaths}
        />
      )
      fireEvent.click(screen.getByTestId('archive-path-selector'))
      fireEvent.click(screen.getByRole('button', { name: /restore selection/i }))
      expect(onRestorePaths).toHaveBeenCalledWith(
        ['home/karan/docs/invoices.xlsx'],
        expect.any(Array)
      )
      expect(screen.queryByRole('button', { name: /^restore$/i })).not.toBeInTheDocument()
    })

    it('does not intercept Enter while focus is inside a text input', () => {
      renderTab()
      const input = document.createElement('input')
      document.body.appendChild(input)
      input.focus()
      fireEvent.keyDown(input, { key: 'ArrowDown' })
      expect(screen.queryByText(/selected/i)).not.toBeInTheDocument()
      document.body.removeChild(input)
    })

    it('keeps an earlier mouse selection when a later row is opened by keyboard', () => {
      const root = renderTab()
      // A file picked with the mouse, then a second one with the keyboard:
      // the selector's published callback must see the first selection.
      fireEvent.click(screen.getByTestId('archive-path-selector'))
      fireEvent.keyDown(root, { key: 'ArrowDown' })
      fireEvent.keyDown(root, { key: 'Enter' })
      expect(screen.getByText(/2 selected/i)).toBeInTheDocument()
    })

    it('drives the visible cursor so arrow keys have something to move', () => {
      const root = renderTab()
      fireEvent.keyDown(root, { key: 'ArrowDown' })
      expect(lastActiveIndex).toBe(1)
      fireEvent.keyDown(root, { key: 'ArrowUp' })
      expect(lastActiveIndex).toBe(0)
    })

    it('keeps the cursor hidden until the keyboard is used and hides it again on a click', () => {
      const root = renderTab()
      expect(lastActiveIndex).toBeUndefined()
      fireEvent.keyDown(root, { key: 'ArrowDown' })
      expect(lastActiveIndex).toBe(1)
      fireEvent.mouseDown(screen.getByTestId('archive-path-selector'))
      expect(lastActiveIndex).toBeUndefined()
    })

    it('focuses the folder filter on "/"', () => {
      const root = renderTab()
      focusFilterSpy.mockClear()
      fireEvent.keyDown(root, { key: '/' })
      expect(focusFilterSpy).toHaveBeenCalled()
    })

    it('opens restore for the selection on "r"', () => {
      const onRestorePaths = vi.fn()
      const { container } = renderWithProviders(
        <ArchiveFilesTab
          repositoryId={7}
          repository={repository}
          archive={archive}
          onRestorePaths={onRestorePaths}
        />
      )
      const root = container.firstChild as HTMLElement
      fireEvent.click(screen.getByTestId('archive-path-selector'))
      fireEvent.keyDown(root, { key: 'r' })
      expect(onRestorePaths).toHaveBeenCalledWith(
        ['home/karan/docs/invoices.xlsx'],
        expect.any(Array)
      )
    })
  })
})
