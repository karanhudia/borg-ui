import { Box, Stack, Tooltip, Typography, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { startOfWeek, addDays, differenceInCalendarWeeks, parseISO } from 'date-fns'
import { formatBytes, formatDurationSeconds } from '../../utils/dateUtils'
import type { HeatmapDay, HeatmapResponse, HeatmapSeries } from '../../types/archives'

interface ArchiveSeriesHeatmapProps {
  data: HeatmapResponse
  onSelectDay: (day: HeatmapDay) => void
}

const MAX_COUNT_STEP = 4

function countScale(count: number): number {
  if (count <= 0) return 0
  const step = Math.min(count, MAX_COUNT_STEP)
  return 0.15 + (step / MAX_COUNT_STEP) * 0.8
}

function buildWeeks(days: HeatmapDay[]): (HeatmapDay | null)[][] {
  const byDate = new Map(days.map((day) => [day.date, day]))
  if (days.length === 0) return []

  const sortedDates = [...byDate.keys()].sort()
  const first = parseISO(sortedDates[0])
  const last = parseISO(sortedDates[sortedDates.length - 1])
  const gridStart = startOfWeek(first, { weekStartsOn: 1 })
  const weekCount = differenceInCalendarWeeks(last, gridStart, { weekStartsOn: 1 }) + 1

  const weeks: (HeatmapDay | null)[][] = []
  for (let w = 0; w < weekCount; w++) {
    const week: (HeatmapDay | null)[] = []
    for (let d = 0; d < 7; d++) {
      const date = addDays(gridStart, w * 7 + d)
      const iso = date.toISOString().slice(0, 10)
      week.push(byDate.get(iso) ?? null)
    }
    weeks.push(week)
  }
  return weeks
}

function SeriesBlock({
  series,
  onSelectDay,
}: {
  series: HeatmapSeries
  onSelectDay: (day: HeatmapDay) => void
}) {
  const { t } = useTranslation()
  const theme = useTheme()
  const weeks = buildWeeks(series.days)
  const missedSet = new Set(series.missed_days)

  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2">{series.series}</Typography>
      {weeks.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t('archives.heatmap.none')}
        </Typography>
      ) : (
        <Stack spacing={0.5}>
          {weeks.map((week, weekIndex) => (
            <Stack key={weekIndex} direction="row" spacing={0.5}>
              {week.map((day, dayIndex) => {
                if (!day) {
                  return <Box key={dayIndex} sx={{ width: 14, height: 14 }} />
                }
                const missed = missedSet.has(day.date)
                const hasArchives = day.archive_ids.length > 0
                const hasAnomalies = day.anomalies.length > 0
                const cell = (
                  <Box
                    data-testid={`heatmap-day-${series.series}-${day.date}`}
                    data-missed={missed}
                    role={hasArchives ? 'button' : undefined}
                    tabIndex={hasArchives ? 0 : undefined}
                    onClick={hasArchives ? () => onSelectDay(day) : undefined}
                    onKeyDown={
                      hasArchives
                        ? (event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault()
                              onSelectDay(day)
                            }
                          }
                        : undefined
                    }
                    sx={{
                      width: 14,
                      height: 14,
                      borderRadius: 0.5,
                      cursor: hasArchives ? 'pointer' : 'default',
                      backgroundColor: alpha(theme.palette.primary.main, countScale(day.count)),
                      outline: hasAnomalies ? `2px solid ${theme.palette.warning.main}` : 'none',
                      outlineOffset: hasAnomalies ? '1px' : undefined,
                      border: missed ? `1px dashed ${theme.palette.error.main}` : 'none',
                    }}
                  />
                )
                return (
                  <Tooltip
                    key={dayIndex}
                    title={t('archives.heatmap.tooltip', {
                      count: day.count,
                      date: day.date,
                      size: formatBytes(day.deduplicated_size),
                      duration: formatDurationSeconds(day.duration_seconds),
                    })}
                  >
                    {cell}
                  </Tooltip>
                )
              })}
            </Stack>
          ))}
        </Stack>
      )}
    </Stack>
  )
}

export default function ArchiveSeriesHeatmap({ data, onSelectDay }: ArchiveSeriesHeatmapProps) {
  return (
    <Stack spacing={3}>
      {data.series.map((series) => (
        <SeriesBlock key={series.series} series={series} onSelectDay={onSelectDay} />
      ))}
    </Stack>
  )
}
