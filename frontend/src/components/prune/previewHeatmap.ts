import type {
  HeatmapDay,
  HeatmapResponse,
  HeatmapSeries,
  PrunePreviewArchive,
} from '../../types/archives'

const isoDay = (start: string) => start.slice(0, 10)

function band(archives: PrunePreviewArchive[]) {
  const days = new Map<string, HeatmapDay>()
  for (const a of archives) {
    if (!a.start) continue
    const key = isoDay(a.start)
    const day = days.get(key) ?? {
      date: key,
      count: 0,
      deduplicated_size: 0,
      duration_seconds: 0,
      archive_ids: [],
      anomalies: [],
    }
    day.count += 1
    day.deduplicated_size += a.deduplicated_size ?? 0
    if (a.id != null) day.archive_ids.push(a.id)
    days.set(key, day)
  }
  const dated = archives.filter((a) => a.start).sort((x, y) => x.start!.localeCompare(y.start!))
  return {
    days: [...days.values()],
    first: dated[0]?.start ?? null,
    last: dated[dated.length - 1]?.start ?? null,
    count: dated.length,
  }
}

export function previewToHeatmap(archives: PrunePreviewArchive[]): HeatmapResponse {
  const bySeries = new Map<string, PrunePreviewArchive[]>()
  for (const a of archives) {
    if (!a.start || !a.series) continue
    bySeries.set(a.series, [...(bySeries.get(a.series) ?? []), a])
  }
  const series: HeatmapSeries[] = [...bySeries.entries()]
    .sort(([x], [y]) => x.localeCompare(y))
    .map(([name, list]) => ({ series: name, ...band(list) }))
  return {
    since: null,
    until: null,
    repository: { ...band(archives), missed_days: [] },
    series,
    cadence_known: false,
    retention_since: null,
    flags_available: { missed_run: false, size_outlier: false, duration_outlier: false },
  }
}

export function dayVerdict(archives: PrunePreviewArchive[]) {
  const byId = new Map(
    archives.filter((a) => a.id !== null).map((a) => [a.id as number, a.verdict])
  )
  return (day: HeatmapDay): 'kept' | 'deleted' | 'mixed' | undefined => {
    const verdicts = new Set(day.archive_ids.map((id) => byId.get(id)).filter(Boolean))
    if (verdicts.size === 0) return undefined
    if (verdicts.size > 1) return 'mixed'
    return verdicts.has('deleted') ? 'deleted' : 'kept'
  }
}

const MIN_INTENSITY = 0.45

export function sizeIntensity(archives: PrunePreviewArchive[]) {
  const byId = new Map(
    archives.filter((a) => a.id !== null).map((a) => [a.id as number, a.deduplicated_size])
  )
  const perDay = new Map<string, number>()
  for (const a of archives) {
    if (!a.start) continue
    const key = isoDay(a.start)
    perDay.set(key, (perDay.get(key) ?? 0) + (a.deduplicated_size ?? 0))
  }
  const max = Math.max(0, ...perDay.values())
  return (day: HeatmapDay): number => {
    if (max === 0) return MIN_INTENSITY
    const total = day.archive_ids.reduce((sum, id) => sum + (byId.get(id) ?? 0), 0)
    return MIN_INTENSITY + Math.min(1, total / max) * (1 - MIN_INTENSITY)
  }
}
