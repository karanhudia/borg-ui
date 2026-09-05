import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Box,
  ListItemText,
  Menu,
  MenuItem,
  Stack,
  Tooltip,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { useTranslation } from 'react-i18next'
import { addDays, format, startOfDay, subDays } from 'date-fns'
import { formatBytes, parseBackendDate } from '../../utils/dateUtils'
import { HOURLY_WEEKS } from './heatmapScale'
import type { ArchiveRow } from '../../types/archives'

interface ArchiveHourlyHeatmapProps {
  archives: ArchiveRow[]
  onSelectArchive: (archiveId: number) => void
  weeks?: number
}

const MIN_CELL = 10
const MAX_CELL = 18
const GAP = 2
const LABEL_WIDTH = 200
const HOUR_WIDTH = 30
const HOURS = 24

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

interface HourCell {
  archives: ArchiveRow[]
}

function countScale(count: number): number {
  if (count <= 0) return 0
  return 0.35 + (Math.min(count, 3) / 3) * 0.6
}

export default function ArchiveHourlyHeatmap({
  archives,
  onSelectArchive,
  weeks = HOURLY_WEEKS,
}: ArchiveHourlyHeatmapProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const [scrollRef, containerWidth] = useContainerWidth()
  const [chooser, setChooser] = useState<{ anchor: HTMLElement; cell: HourCell } | null>(null)

  const today = useMemo(() => startOfDay(new Date()), [])
  const dayCount = weeks * 7
  const start = subDays(today, dayCount - 1)
  const cell = useMemo(() => {
    if (containerWidth <= 0) return MIN_CELL
    const available = containerWidth - LABEL_WIDTH - HOUR_WIDTH - 4
    return Math.max(MIN_CELL, Math.min(MAX_CELL, Math.floor(available / dayCount) - GAP))
  }, [containerWidth, dayCount])

  // series -> "yyyy-MM-dd:HH" -> archives that started in that hour
  const bands = useMemo(() => {
    const bySeries = new Map<string, Map<string, HourCell>>()
    for (const archive of archives) {
      const at = parseBackendDate(archive.start)
      if (at < start) continue
      const key = `${format(at, 'yyyy-MM-dd')}:${at.getHours()}`
      const series = bySeries.get(archive.series) ?? new Map<string, HourCell>()
      const hour = series.get(key) ?? { archives: [] }
      hour.archives.push(archive)
      series.set(key, hour)
      bySeries.set(archive.series, series)
    }
    return [...bySeries.entries()].sort((a, b) => b[1].size - a[1].size)
  }, [archives, start])

  useEffect(() => {
    const node = scrollRef.current
    if (node) node.scrollLeft = node.scrollWidth
  }, [scrollRef, cell])

  const days = Array.from({ length: dayCount }, (_, i) => addDays(start, i))

  if (bands.length === 0) {
    return (
      <Typography variant="body2" sx={{ color: 'text.secondary' }}>
        {t('archives.hourly.none', { count: weeks })}
      </Typography>
    )
  }

  const activate = (target: HTMLElement, hour: HourCell) => {
    if (hour.archives.length === 1) onSelectArchive(hour.archives[0].id)
    else setChooser({ anchor: target, cell: hour })
  }

  return (
    <Stack spacing={2}>
      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
        {t('archives.hourly.window', { count: weeks })}
      </Typography>
      <Box ref={scrollRef} sx={{ overflowX: 'auto', pb: 1, bgcolor: 'background.paper' }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-end', mb: 0.5 }}>
          <Box
            sx={{
              width: LABEL_WIDTH + HOUR_WIDTH,
              flexShrink: 0,
              position: 'sticky',
              left: 0,
              bgcolor: 'background.paper',
              zIndex: 1,
              height: 18,
            }}
          />
          <Box
            data-testid="hourly-day-axis"
            sx={{
              display: 'grid',
              gridTemplateColumns: `repeat(${dayCount}, ${cell}px)`,
              gap: `${GAP}px`,
            }}
          >
            {days.map((day, index) => {
              // Mondays carry the label; the first column only when the next
              // Monday is more than two days away, so labels never collide.
              const daysToMonday = (8 - day.getDay()) % 7
              const showLabel = day.getDay() === 1 || (index === 0 && daysToMonday > 2)
              return (
                <Typography
                  key={day.toISOString()}
                  variant="caption"
                  sx={{
                    color: 'text.secondary',
                    lineHeight: '18px',
                    whiteSpace: 'nowrap',
                    fontSize: 10,
                    overflow: 'visible',
                  }}
                >
                  {showLabel ? format(day, 'd MMM') : ''}
                </Typography>
              )
            })}
          </Box>
        </Box>
        <Stack spacing={2}>
          {bands.map(([series, hours]) => (
            <Box key={series} sx={{ display: 'flex', alignItems: 'flex-start' }}>
              <Typography
                variant="body2"
                title={series}
                sx={{
                  width: LABEL_WIDTH,
                  flexShrink: 0,
                  pr: 2,
                  fontWeight: 600,
                  lineHeight: 1.3,
                  position: 'sticky',
                  left: 0,
                  bgcolor: 'background.paper',
                  zIndex: 1,
                  display: '-webkit-box',
                  WebkitLineClamp: 3,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                  wordBreak: 'break-word',
                }}
              >
                {series}
              </Typography>
              <Box sx={{ width: HOUR_WIDTH, flexShrink: 0 }}>
                {Array.from({ length: HOURS }, (_, hour) => (
                  <Typography
                    key={hour}
                    variant="caption"
                    sx={{
                      display: 'block',
                      height: cell,
                      lineHeight: `${cell}px`,
                      mb: `${GAP}px`,
                      fontSize: 9,
                      color: 'text.secondary',
                      visibility: hour % 6 === 0 ? 'visible' : 'hidden',
                    }}
                  >
                    {`${String(hour).padStart(2, '0')}:00`}
                  </Typography>
                ))}
              </Box>
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: `repeat(${dayCount}, ${cell}px)`,
                  gridTemplateRows: `repeat(${HOURS}, ${cell}px)`,
                  gridAutoFlow: 'column',
                  gap: `${GAP}px`,
                }}
              >
                {days.flatMap((day) =>
                  Array.from({ length: HOURS }, (_, hour) => {
                    const iso = format(day, 'yyyy-MM-dd')
                    const entry = hours.get(`${iso}:${hour}`)
                    const count = entry?.archives.length ?? 0
                    const box = (
                      <Box
                        key={`${iso}:${hour}`}
                        data-testid={`hourly-cell-${series}-${iso}-${hour}`}
                        data-count={count}
                        role={count > 0 ? 'button' : undefined}
                        tabIndex={count > 0 ? 0 : undefined}
                        onClick={
                          entry ? (event) => activate(event.currentTarget, entry) : undefined
                        }
                        onKeyDown={
                          entry
                            ? (event) => {
                                if (event.key === 'Enter' || event.key === ' ') {
                                  event.preventDefault()
                                  activate(event.currentTarget, entry)
                                }
                              }
                            : undefined
                        }
                        sx={{
                          width: cell,
                          height: cell,
                          borderRadius: cell >= 14 ? '3px' : '2px',
                          cursor: count > 0 ? 'pointer' : 'default',
                          bgcolor:
                            count > 0
                              ? alpha(theme.palette.primary.main, countScale(count))
                              : alpha(theme.palette.text.primary, hour % 6 === 0 ? 0.08 : 0.05),
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: Math.max(8, cell - 6),
                          fontWeight: 700,
                          color: theme.palette.primary.contrastText,
                          '&:focus-visible': {
                            outline: `2px solid ${theme.palette.primary.main}`,
                            outlineOffset: 1,
                          },
                        }}
                      >
                        {cell >= 14 && count > 1 ? count : null}
                      </Box>
                    )
                    if (!entry) return box
                    const first = entry.archives[0]
                    return (
                      <Tooltip
                        key={`${iso}:${hour}`}
                        title={t('archives.hourly.tooltip', {
                          count,
                          time: parseBackendDate(first.start).toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit',
                          }),
                          date: iso,
                        })}
                      >
                        {box}
                      </Tooltip>
                    )
                  })
                )}
              </Box>
            </Box>
          ))}
        </Stack>
      </Box>
      <Menu open={chooser != null} anchorEl={chooser?.anchor} onClose={() => setChooser(null)}>
        {chooser?.cell.archives.map((archive) => (
          <MenuItem
            key={archive.id}
            onClick={() => {
              setChooser(null)
              onSelectArchive(archive.id)
            }}
          >
            <ListItemText
              primary={parseBackendDate(archive.start).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
              secondary={`${archive.name}${archive.deduplicated_size != null ? ` · ${formatBytes(archive.deduplicated_size)}` : ''}`}
            />
          </MenuItem>
        ))}
      </Menu>
    </Stack>
  )
}
