import { useEffect, useMemo, useRef, useState } from 'react'
import { Box, Button, Stack, Tooltip, Typography, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { addDays, addWeeks, format, max, min, parseISO, startOfWeek, subWeeks } from 'date-fns'
import HeatmapLegend from './HeatmapLegend'
import { formatBytes, formatDurationSeconds } from '../../utils/dateUtils'
import type { HeatmapDay, HeatmapResponse, HeatmapSeries } from '../../types/archives'

interface ArchiveSeriesHeatmapProps {
  data: HeatmapResponse
  onSelectDay: (day: HeatmapDay) => void
}

// Calendar geometry: columns are weeks, rows are weekdays, so a year is
// 53 columns wide and seven cells tall, and every series band shares one
// month axis at the top.
// Cells grow with the panel: at least 10 px so a year fits on a laptop,
// at most 18 px so the calendar stays a calendar on a wide monitor.
const MIN_CELL = 10
const MAX_CELL = 18
export const GAP = 2
const LABEL_WIDTH = 200
const WEEKDAY_WIDTH = 18
const WEEKS_BY_DEFAULT = 52
const MAX_COUNT_STEP = 4
// A series with fewer archives than this is folded behind a disclosure so a
// mis-inferred name (spec 6.6) does not push real series off the screen.
export const SMALL_SERIES_THRESHOLD = 5

function countScale(count: number): number {
  if (count <= 0) return 0
  const step = Math.min(count, MAX_COUNT_STEP)
  return 0.25 + (step / MAX_COUNT_STEP) * 0.7
}

const isoDay = (date: Date) => format(date, 'yyyy-MM-dd')

interface Window {
  start: Date
  weeks: number
  today: Date
  cell: number
}

function useContainerWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const node = ref.current
    if (!node || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => {
      setWidth(Math.floor(entries[0]?.contentRect.width ?? 0))
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [])
  return [ref, width]
}

function cellSizeFor(containerWidth: number, weeks: number): number {
  if (containerWidth <= 0 || weeks <= 0) return MIN_CELL
  const available = containerWidth - LABEL_WIDTH - WEEKDAY_WIDTH - 4
  return Math.max(MIN_CELL, Math.min(MAX_CELL, Math.floor(available / weeks) - GAP))
}

function buildWindow(series: HeatmapSeries[], today: Date, cell: number): Window {
  const dates = series.flatMap((s) => [...s.days.map((d) => d.date), ...s.missed_days])
  const earliest = dates.length > 0 ? min(dates.map((d) => parseISO(d))) : today
  const defaultStart = subWeeks(today, WEEKS_BY_DEFAULT - 1)
  const start = startOfWeek(min([earliest, defaultStart]), { weekStartsOn: 1 })
  const end = startOfWeek(max([today, ...dates.map((d) => parseISO(d))]), { weekStartsOn: 1 })
  const weeks = Math.round((end.getTime() - start.getTime()) / (7 * 24 * 3600 * 1000)) + 1
  return { start, weeks, today, cell }
}

function MonthAxis({ window }: { window: Window }) {
  const weekWidth = window.cell + GAP
  const labels: { column: number; label: string }[] = []
  let lastMonth = -1
  for (let w = 0; w < window.weeks; w++) {
    const weekStart = addWeeks(window.start, w)
    const month = weekStart.getMonth()
    if (month !== lastMonth) {
      labels.push({ column: w, label: weekStart.toLocaleDateString([], { month: 'short' }) })
      lastMonth = month
    }
  }
  return (
    <Box
      data-testid="heatmap-month-axis"
      sx={{ position: 'relative', height: 18, width: window.weeks * weekWidth }}
    >
      {labels.map(({ column, label }, index) => {
        // A month that starts in the last column has no room for its label.
        const nextColumn = labels[index + 1]?.column ?? window.weeks
        if (nextColumn - column < 3) return null
        return (
          <Typography
            key={`${label}-${column}`}
            variant="caption"
            sx={{
              position: 'absolute',
              left: column * weekWidth,
              color: 'text.secondary',
              lineHeight: '18px',
            }}
          >
            {label}
          </Typography>
        )
      })}
    </Box>
  )
}

function WeekdayColumn({ cell }: { cell: number }) {
  const monday = startOfWeek(new Date(), { weekStartsOn: 1 })
  return (
    <Box sx={{ width: WEEKDAY_WIDTH, flexShrink: 0 }}>
      {[0, 1, 2, 3, 4, 5, 6].map((offset) => (
        <Typography
          key={offset}
          variant="caption"
          sx={{
            display: 'block',
            height: cell,
            lineHeight: `${cell}px`,
            fontSize: cell >= 14 ? 10 : 8,
            mb: `${GAP}px`,
            color: 'text.secondary',
            visibility: offset % 2 === 0 ? 'visible' : 'hidden',
          }}
        >
          {addDays(monday, offset).toLocaleDateString([], { weekday: 'narrow' })}
        </Typography>
      ))}
    </Box>
  )
}

function SeriesBand({
  series,
  window,
  onSelectDay,
}: {
  series: HeatmapSeries
  window: Window
  onSelectDay: (day: HeatmapDay) => void
}) {
  const { t } = useTranslation()
  const theme = useTheme()
  const byDate = useMemo(() => new Map(series.days.map((d) => [d.date, d])), [series.days])
  const missed = useMemo(() => new Set(series.missed_days), [series.missed_days])
  const todayIso = isoDay(window.today)

  return (
    <Box sx={{ display: 'flex', alignItems: 'flex-start' }}>
      <Typography
        variant="body2"
        title={series.series}
        sx={{
          width: LABEL_WIDTH,
          flexShrink: 0,
          pr: 2,
          fontWeight: 600,
          lineHeight: 1.3,
          mt: '-2px',
          display: '-webkit-box',
          WebkitLineClamp: 3,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
          wordBreak: 'break-word',
          position: 'sticky',
          left: 0,
          bgcolor: 'background.paper',
          zIndex: 1,
        }}
      >
        {series.series}
      </Typography>
      <WeekdayColumn cell={window.cell} />
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: `repeat(${window.weeks}, ${window.cell}px)`,
          gridTemplateRows: `repeat(7, ${window.cell}px)`,
          gridAutoFlow: 'column',
          gap: `${GAP}px`,
        }}
      >
        {Array.from({ length: window.weeks * 7 }, (_, index) => {
          const date = addDays(window.start, index)
          const iso = isoDay(date)
          if (iso > todayIso) return <Box key={iso} />
          const day = byDate.get(iso)
          const count = day?.count ?? 0
          const hasArchives = (day?.archive_ids.length ?? 0) > 0
          const hasAnomalies = (day?.anomalies.length ?? 0) > 0
          const isMissed = missed.has(iso)
          const cell = (
            <Box
              key={iso}
              data-testid={`heatmap-day-${series.series}-${iso}`}
              data-missed={isMissed}
              data-count={count}
              role={hasArchives ? 'button' : undefined}
              tabIndex={hasArchives ? 0 : undefined}
              aria-label={
                hasArchives
                  ? t('archives.heatmap.tooltip', {
                      count,
                      date: iso,
                      size: formatBytes(day?.deduplicated_size ?? 0),
                      duration: formatDurationSeconds(day?.duration_seconds ?? 0),
                    })
                  : undefined
              }
              onClick={hasArchives && day ? () => onSelectDay(day) : undefined}
              onKeyDown={
                hasArchives && day
                  ? (event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        onSelectDay(day)
                      }
                    }
                  : undefined
              }
              sx={{
                width: window.cell,
                height: window.cell,
                borderRadius: window.cell >= 14 ? '3px' : '2px',
                boxSizing: 'border-box',
                cursor: hasArchives ? 'pointer' : 'default',
                bgcolor: hasArchives
                  ? alpha(theme.palette.primary.main, countScale(count))
                  : alpha(theme.palette.text.primary, 0.06),
                border: isMissed ? `1px dashed ${alpha(theme.palette.error.main, 0.55)}` : 'none',
                boxShadow: hasAnomalies ? `inset 0 0 0 2px ${theme.palette.warning.main}` : 'none',
                '&:focus-visible': {
                  outline: `2px solid ${theme.palette.primary.main}`,
                  outlineOffset: 1,
                },
              }}
            />
          )
          if (!hasArchives && !isMissed) return cell
          return (
            <Tooltip
              key={iso}
              title={
                hasArchives
                  ? t('archives.heatmap.tooltip', {
                      count,
                      date: iso,
                      size: formatBytes(day?.deduplicated_size ?? 0),
                      duration: formatDurationSeconds(day?.duration_seconds ?? 0),
                    })
                  : t('archives.heatmap.missed')
              }
            >
              {cell}
            </Tooltip>
          )
        })}
      </Box>
    </Box>
  )
}

export default function ArchiveSeriesHeatmap({ data, onSelectDay }: ArchiveSeriesHeatmapProps) {
  const { t } = useTranslation()
  const [showSmall, setShowSmall] = useState(false)
  const [scrollRef, containerWidth] = useContainerWidth()
  const today = useMemo(() => new Date(), [])
  const weeks = useMemo(() => buildWindow(data.series, today, MIN_CELL).weeks, [data.series, today])
  const cell = cellSizeFor(containerWidth, weeks)
  const window = useMemo(() => buildWindow(data.series, today, cell), [data.series, today, cell])

  const archiveCount = (series: HeatmapSeries) =>
    series.days.reduce((sum, day) => sum + day.count, 0)
  const large = data.series.filter((s) => archiveCount(s) >= SMALL_SERIES_THRESHOLD)
  const small = data.series.filter((s) => archiveCount(s) < SMALL_SERIES_THRESHOLD)
  // With nothing above the threshold there is nothing to fold behind.
  const visible = large.length === 0 ? data.series : showSmall ? [...large, ...small] : large
  const folded = large.length === 0 ? [] : small

  useEffect(() => {
    // The newest week sits at the right edge, which is where the eye
    // should land.
    const node = scrollRef.current
    if (node) node.scrollLeft = node.scrollWidth
  }, [window.weeks, window.cell, scrollRef])

  return (
    <Stack spacing={2}>
      <Box ref={scrollRef} sx={{ overflowX: 'auto', pb: 1, bgcolor: 'background.paper' }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', mb: 0.5 }}>
          <Box
            sx={{
              width: LABEL_WIDTH + WEEKDAY_WIDTH,
              flexShrink: 0,
              position: 'sticky',
              left: 0,
              bgcolor: 'background.paper',
              zIndex: 1,
              height: 18,
            }}
          />
          <MonthAxis window={window} />
        </Box>
        <Stack spacing={1.5}>
          {visible.map((series) => (
            <SeriesBand
              key={series.series}
              series={series}
              window={window}
              onSelectDay={onSelectDay}
            />
          ))}
        </Stack>
      </Box>
      {folded.length > 0 && (
        <Box>
          <Button size="small" variant="text" onClick={() => setShowSmall((value) => !value)}>
            {showSmall
              ? t('archives.heatmap.hideSmaller')
              : t('archives.heatmap.showSmaller', { count: folded.length })}
          </Button>
          {showSmall && (
            <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>
              {t('archives.heatmap.smallerNote', { count: SMALL_SERIES_THRESHOLD })}
            </Typography>
          )}
        </Box>
      )}
      <HeatmapLegend flagsAvailable={data.flags_available} />
    </Stack>
  )
}
