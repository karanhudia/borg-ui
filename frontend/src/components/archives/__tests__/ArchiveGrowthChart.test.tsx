import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import ArchiveGrowthChart from '../ArchiveGrowthChart'
import type { GrowthPoint, GrowthResponse } from '../../../types/archives'

const point = (id: number, day: number, overrides: Partial<GrowthPoint> = {}): GrowthPoint => ({
  archive_id: id,
  name: `nas-2026-09-0${day}`,
  series: 'nas',
  start: `2026-09-0${day}T02:00:00`,
  deduplicated_size: 1_000_000_000,
  original_size: 90_000_000_000,
  running_total: id * 1_000_000_000,
  repository_size: id * 20_000_000_000,
  stale: false,
  ...overrides,
})

const response = (overrides: Partial<GrowthResponse> = {}): GrowthResponse => ({
  points: [point(1, 1), point(2, 2), point(3, 3)],
  series: ['nas'],
  stale_count: 0,
  unmeasured_count: 0,
  ...overrides,
})

const render = (data: GrowthResponse) => {
  const onSelectArchive = vi.fn()
  renderWithProviders(<ArchiveGrowthChart data={data} onSelectArchive={onSelectArchive} />)
  return { onSelectArchive }
}

describe('ArchiveGrowthChart', () => {
  it('names the repository line and the source line', () => {
    render(response())
    expect(screen.getByText('Repository size after this backup')).toBeInTheDocument()
    expect(screen.getByText('Source size (before deduplication)')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('explains stale and unmeasured archives', () => {
    render(
      response({
        points: [point(1, 1), point(2, 2, { stale: true }), point(3, 3)],
        stale_count: 1,
        unmeasured_count: 2,
      })
    )
    expect(screen.getByText(/1 archive is being re-measured/)).toBeInTheDocument()
    expect(screen.getByText(/2 archives are not measured yet/)).toBeInTheDocument()
  })

  it('shows the whole repository, with no series select', () => {
    render(response({ series: ['nas', 'docs'] }))
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('says so when fewer than two archives are measured', () => {
    render(response({ points: [point(1, 1)] }))
    expect(
      screen.getByText('The growth graph needs at least two measured archives.')
    ).toBeInTheDocument()
    expect(screen.queryByText('Added per archive')).not.toBeInTheDocument()
  })
})
