import { describe, expect, it } from 'vitest'
import { dayVerdict, previewToHeatmap, sizeIntensity } from '../previewHeatmap'
import type { PrunePreviewArchive } from '../../../types/archives'

const a = (
  id: number,
  series: string,
  start: string,
  verdict: 'kept' | 'deleted',
  size: number | null
): PrunePreviewArchive => ({
  id,
  borg_id: `${id}`,
  name: `a${id}`,
  series,
  start,
  verdict,
  rule: verdict === 'kept' ? 'daily #1' : null,
  deduplicated_size: size,
  stats_measured_at: null,
  stale: false,
})

describe('previewToHeatmap', () => {
  it('groups archives into a repository band and one band per series', () => {
    const data = previewToHeatmap([
      a(1, 'nas', '2026-09-10T02:00:00', 'kept', 10),
      a(2, 'docs', '2026-09-10T03:00:00', 'deleted', 20),
    ])
    expect(data.repository.days.map((d) => d.archive_ids)).toEqual([[1, 2]])
    expect(data.series.map((s) => s.series)).toEqual(['docs', 'nas'])
    expect(data.repository.count).toBe(2)
  })
  it('skips archives without a start', () => {
    expect(
      previewToHeatmap([a(1, 'nas', null as unknown as string, 'kept', 1)]).repository.count
    ).toBe(0)
  })
})

describe('dayVerdict', () => {
  it('is kept, deleted or mixed', () => {
    const list = [
      a(1, 'nas', '2026-09-10T02:00:00', 'kept', 1),
      a(2, 'nas', '2026-09-10T03:00:00', 'deleted', 1),
      a(3, 'nas', '2026-09-11T02:00:00', 'deleted', 1),
    ]
    const verdict = dayVerdict(list)
    expect(
      verdict({
        date: '2026-09-10',
        archive_ids: [1, 2],
        count: 2,
        deduplicated_size: 0,
        duration_seconds: 0,
        anomalies: [],
      })
    ).toBe('mixed')
    expect(
      verdict({
        date: '2026-09-11',
        archive_ids: [3],
        count: 1,
        deduplicated_size: 0,
        duration_seconds: 0,
        anomalies: [],
      })
    ).toBe('deleted')
  })
})

describe('sizeIntensity', () => {
  it('scales the largest day to 1 and the smallest to 0.45, unmeasured to 0.45', () => {
    const list = [
      a(1, 'nas', '2026-09-10T02:00:00', 'kept', 100),
      a(2, 'nas', '2026-09-11T02:00:00', 'kept', 0),
      a(3, 'nas', '2026-09-12T02:00:00', 'kept', null),
    ]
    const f = sizeIntensity(list)
    const day = (date: string, ids: number[]) => ({
      date,
      archive_ids: ids,
      count: ids.length,
      deduplicated_size: 0,
      duration_seconds: 0,
      anomalies: [],
    })
    expect(f(day('2026-09-10', [1]))).toBe(1)
    expect(f(day('2026-09-11', [2]))).toBe(0.45)
    expect(f(day('2026-09-12', [3]))).toBe(0.45)
  })
})

describe('sizeIntensity', () => {
  it('normalises against the largest day, not the largest archive', () => {
    const list = [
      a(1, 'nas', '2026-09-10T02:00:00', 'deleted', 10),
      a(2, 'nas', '2026-09-10T03:00:00', 'deleted', 10),
      a(3, 'nas', '2026-09-11T02:00:00', 'deleted', 10),
    ]
    const intensity = sizeIntensity(list)
    const day = (ids: number[]) => ({
      date: '2026-09-10',
      archive_ids: ids,
      count: ids.length,
      deduplicated_size: 0,
      duration_seconds: 0,
      anomalies: [],
    })
    expect(intensity(day([1, 2]))).toBe(1)
    expect(intensity(day([3]))).toBeCloseTo(0.725)
  })
})
