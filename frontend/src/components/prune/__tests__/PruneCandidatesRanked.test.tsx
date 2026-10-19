import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/test-utils'
import PruneCandidatesRanked from '../PruneCandidatesRanked'
import { formatDate } from '../../../utils/dateUtils'
import type { PrunePreviewArchive } from '../../../types/archives'

const archive = (id: number | null, name: string): PrunePreviewArchive => ({
  id,
  borg_id: name,
  name,
  series: 'nas',
  start: '2026-09-01T02:00:00',
  verdict: 'deleted',
  rule: null,
  deduplicated_size: 10,
  stats_measured_at: '2026-09-17T09:00:00',
  stale: false,
})

describe('PruneCandidatesRanked', () => {
  it('rows are buttons that open the archive from the keyboard', async () => {
    const onOpen = vi.fn()
    renderWithProviders(
      <PruneCandidatesRanked
        archives={[archive(1, 'a1'), archive(null, 'unknown')]}
        partialMeasure={false}
        onOpen={onOpen}
      />
    )
    const row = screen.getByRole('button', { name: /a1/ })
    row.focus()
    await userEvent.keyboard('{Enter}')
    expect(onOpen).toHaveBeenCalledTimes(1)
    expect(onOpen).toHaveBeenCalledWith(1)
    expect(screen.queryByRole('button', { name: /unknown/ })).not.toBeInTheDocument()
  })

  it('shows five rows and a Show all button for the rest', async () => {
    const archives = Array.from({ length: 8 }, (_, i) => archive(i + 1, `a${i + 1}`))
    renderWithProviders(
      <PruneCandidatesRanked archives={archives} partialMeasure={false} onOpen={() => {}} />
    )
    expect(screen.getAllByRole('button', { name: /\ba\d+\b/ })).toHaveLength(5)
    await userEvent.click(screen.getByRole('button', { name: /show all 8/i }))
    expect(screen.getAllByRole('button', { name: /\ba\d+\b/ })).toHaveLength(8)
  })

  it('lists Borg 2 candidates in payload order without ranks, sizes or re-measure', () => {
    // #1351: no per-archive size a deletion would free, so nothing to rank by
    const sized = (id: number, start: string, size: number) => ({
      ...archive(id, 'daily'),
      borg_id: `${id}`,
      start,
      deduplicated_size: size,
      stats_measured_at: null,
      stale: true,
    })
    renderWithProviders(
      <PruneCandidatesRanked
        archives={[sized(1, '2026-08-30T02:00:00', 1), sized(2, '2026-08-31T02:00:00', 9)]}
        partialMeasure={false}
        sizesAvailable={false}
        onOpen={() => {}}
      />
    )
    expect(screen.getByText('Deleted archives')).toBeInTheDocument()
    expect(screen.getByText(/Borg 2 reports no per-archive size/)).toBeInTheDocument()
    expect(screen.queryByText(/re-measur/i)).not.toBeInTheDocument()
    // a series shares its name, so each row carries its time (in the
    // reader's zone), in payload order
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual([
      `daily${formatDate('2026-08-30T02:00:00')}`,
      `daily${formatDate('2026-08-31T02:00:00')}`,
    ])
  })
})
