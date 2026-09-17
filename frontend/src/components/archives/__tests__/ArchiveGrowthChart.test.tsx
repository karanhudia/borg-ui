import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
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

const render = (data: GrowthResponse, series = '') => {
  const onSeriesChange = vi.fn()
  const onSelectArchive = vi.fn()
  renderWithProviders(
    <ArchiveGrowthChart
      data={data}
      series={series}
      onSeriesChange={onSeriesChange}
      onSelectArchive={onSelectArchive}
    />
  )
  return { onSeriesChange, onSelectArchive }
}

describe('ArchiveGrowthChart', () => {
  it('names the bars and the footprint line, and hides the source line by default', () => {
    render(response())
    expect(screen.getByText('Added per archive')).toBeInTheDocument()
    expect(screen.getByText('Repository footprint (running total, at least)')).toBeInTheDocument()
    expect(screen.queryByText('Source size (original)')).not.toBeInTheDocument()
    expect(screen.queryByText('Stale, re-measuring')).not.toBeInTheDocument()
  })

  it('adds the source line when asked', () => {
    render(response())
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show source size' }))
    expect(screen.getByText('Source size (original)')).toBeInTheDocument()
  })

  it('explains stale and unmeasured archives', () => {
    render(
      response({
        points: [point(1, 1), point(2, 2, { stale: true }), point(3, 3)],
        stale_count: 1,
        unmeasured_count: 2,
      })
    )
    expect(screen.getByText('Stale, re-measuring')).toBeInTheDocument()
    expect(screen.getByText(/1 archive is being re-measured/)).toBeInTheDocument()
    expect(screen.getByText(/2 archives are not measured yet/)).toBeInTheDocument()
  })

  it('offers the series select only when the repository has several series', () => {
    render(response())
    expect(screen.queryByLabelText('Series')).not.toBeInTheDocument()
  })

  it('switches series through the select', () => {
    const { onSeriesChange } = render(response({ series: ['nas', 'docs'] }))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Series/ }))
    fireEvent.click(screen.getByRole('option', { name: /docs/ }))
    expect(onSeriesChange).toHaveBeenCalledWith('docs')
  })

  it('says so when fewer than two archives are measured', () => {
    render(response({ points: [point(1, 1)] }))
    expect(
      screen.getByText('The growth graph needs at least two measured archives.')
    ).toBeInTheDocument()
    expect(screen.queryByText('Added per archive')).not.toBeInTheDocument()
  })
})
