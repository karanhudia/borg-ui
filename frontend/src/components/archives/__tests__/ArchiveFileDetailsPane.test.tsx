import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import ArchiveFileDetailsPane from '../ArchiveFileDetailsPane'

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

describe('ArchiveFileDetailsPane', () => {
  it('shows folder metadata when selectedPath is null', () => {
    renderWithProviders(
      <ArchiveFileDetailsPane
        repositoryId={7}
        selectedPath={null}
        selectedEntry={null}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
      />
    )
    expect(screen.getByText('Folder')).toBeInTheDocument()
  })

  it('shows file metadata when a file is selected', () => {
    renderWithProviders(
      <ArchiveFileDetailsPane
        repositoryId={7}
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
    expect(screen.getByText('invoices.xlsx')).toBeInTheDocument()
  })

  it('leaves the size line out when the size is unknown', () => {
    renderWithProviders(
      <ArchiveFileDetailsPane
        repositoryId={7}
        selectedPath="home/karan/docs/invoices.xlsx"
        selectedEntry={{
          name: 'invoices.xlsx',
          type: 'file',
          path: 'home/karan/docs/invoices.xlsx',
        }}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
      />
    )
    expect(screen.queryByText(/0 B/)).not.toBeInTheDocument()
  })

  it('offers download but no duplicate restore', () => {
    const onRestore = vi.fn()
    const onDownload = vi.fn()
    renderWithProviders(
      <ArchiveFileDetailsPane
        repositoryId={7}
        selectedPath="home/karan/docs/invoices.xlsx"
        selectedEntry={{
          name: 'invoices.xlsx',
          type: 'file',
          path: 'home/karan/docs/invoices.xlsx',
          size: 412_000,
        }}
        onRestore={onRestore}
        onDownload={onDownload}
      />
    )
    expect(screen.queryByRole('button', { name: /^restore$/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^download$/i }))
    expect(onDownload).toHaveBeenCalled()
    expect(onRestore).not.toHaveBeenCalled()
  })
})
