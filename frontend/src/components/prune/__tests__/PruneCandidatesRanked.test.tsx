import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/test-utils'
import PruneCandidatesRanked from '../PruneCandidatesRanked'
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
})
