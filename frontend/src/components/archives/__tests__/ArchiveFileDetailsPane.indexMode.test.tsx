import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import ArchiveFileDetailsPane from '../ArchiveFileDetailsPane'
import type { IndexMode } from '../../../types/operations'

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

function renderPane(indexMode: IndexMode) {
  renderWithProviders(
    <ArchiveFileDetailsPane
      repositoryId={7}
      indexMode={indexMode}
      selectedPath="home/karan/docs/invoices.xlsx"
      selectedEntry={{
        name: 'invoices.xlsx',
        type: 'file',
        path: 'home/karan/docs/invoices.xlsx',
        size: 412_000,
      }}
      onRestore={vi.fn()}
      onDownload={vi.fn()}
    />
  )
}

describe('ArchiveFileDetailsPane index mode (spec 6.8)', () => {
  beforeEach(() => {
    mockPlanCan.mockReturnValue(true)
  })

  it('explains the mode when the plan allows file history', () => {
    renderPane('archives')
    expect(screen.getByText(/archives only/i)).toBeInTheDocument()
  })

  it('leaves the plan gate to answer a Community install', () => {
    // Plan first, then mode, never both. FileHistoryPanel carries its own
    // PlanGate, so gating it from the outside would hand a Community user
    // the mode message in place of the upgrade prompt.
    mockPlanCan.mockReturnValue(false)
    renderPane('archives')
    expect(screen.queryByText(/archives only/i)).not.toBeInTheDocument()
  })

  it('renders the history panel for a repository that indexes it', () => {
    renderPane('full')
    expect(screen.queryByText(/archives only/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/not indexed/i)).not.toBeInTheDocument()
  })
})
