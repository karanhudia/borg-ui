import { describe, expect, it } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import PruneLostFilesPanel from '../PruneLostFilesPanel'

describe('PruneLostFilesPanel', () => {
  it('lists totals, folders and the top files with a link to the archive', () => {
    renderWithProviders(
      <PruneLostFilesPanel
        repositoryId={7}
        lost={{
          available: true,
          capability: 'available',
          incomplete: false,
          unindexed_archive_ids: [],
          total_count: 2,
          total_size: 30,
          top: [
            {
              path: 'docs/x',
              size: 20,
              series: 'nas',
              last_held_archive_id: 4,
              last_held_archive_name: 'a4',
            },
            {
              path: 'docs/y',
              size: 10,
              series: 'nas',
              last_held_archive_id: 4,
              last_held_archive_name: 'a4',
            },
          ],
          by_folder: [{ folder: 'docs', count: 2, size: 30 }],
        }}
      />
    )
    expect(screen.getByText(/2 files/)).toBeInTheDocument()
    expect(screen.getByText('docs/x')).toBeInTheDocument()
    const links = screen.getAllByRole('link', { name: /a4/ })
    expect(links[0]).toHaveAttribute('href', '/archives/7/4')

    fireEvent.change(screen.getByRole('textbox', { name: /filter by path/i }), {
      target: { value: 'docs/Y' },
    })
    expect(screen.queryByText('docs/x')).not.toBeInTheDocument()
    expect(screen.getByText('docs/y')).toBeInTheDocument()
  })

  it('keeps the count and locks the file list on Community', () => {
    // The count is the warning in front of an irreversible delete, so it
    // shows on every plan (spec 2026-09-21, section 1).
    renderWithProviders(
      <PruneLostFilesPanel
        repositoryId={7}
        lost={{
          available: true,
          capability: 'available',
          incomplete: false,
          unindexed_archive_ids: [],
          total_count: 812,
          total_size: 4_200_000_000,
          detail_locked: true,
        }}
      />
    )
    expect(screen.getByText(/812 files/)).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: /filter by path/i })).not.toBeInTheDocument()
    expect(screen.getByText(/Pro lists these files/i)).toBeInTheDocument()
  })

  it('says why when the history index is unavailable', () => {
    renderWithProviders(
      <PruneLostFilesPanel
        repositoryId={7}
        lost={{ available: false, capability: 'agent_unsupported' }}
      />
    )
    expect(screen.getByText(/agent/i)).toBeInTheDocument()
    // The index is what is missing, not the plan: a Pro chip here would
    // offer an upgrade that changes nothing.
    expect(screen.queryByText('Pro')).not.toBeInTheDocument()
  })

  it('warns when the index is incomplete', () => {
    renderWithProviders(
      <PruneLostFilesPanel
        repositoryId={7}
        lost={{
          available: true,
          capability: 'available',
          incomplete: true,
          unindexed_archive_ids: [3, 4],
          total_count: 0,
          total_size: 0,
          top: [],
          by_folder: [],
        }}
      />
    )
    expect(screen.getByText(/index incomplete/i)).toBeInTheDocument()
    expect(screen.queryByText(/No file is lost/)).not.toBeInTheDocument()
    expect(screen.getByText(/not final/i)).toBeInTheDocument()
  })
})
