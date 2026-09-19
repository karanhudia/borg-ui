import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
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
import HeatmapHeader from './HeatmapHeader'
import { HOURLY_WEEKS } from './heatmapScale'
import type { ArchiveRow } from '../../types/archives'

interface ArchiveHourlyHeatmapProps {
  archives: ArchiveRow[]
  onSelectArchive: (archiveId: number) => void
  weeks?: number
  // The same head as the day view: absent, the grid starts at its axis.
  header?: { toolbar?: ReactNode }
}

// Columns are days and stretch to fill the panel, like the day view; rows
// are hours and stay short, so twenty-four of them fit on one screen.
const MIN_CELL = 10
const MAX_COL = 72
const ROW = 16
const GAP = 3
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
  header,
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
    const available = containerWidth - HOUR_WIDTH - 4
    return Math.max(MIN_CELL, Math.min(MAX_COL, Math.floor(available / dayCount) - GAP))
  }, [containerWidth, dayCount])
  const row = Math.min(ROW, cell)

  // "yyyy-MM-dd:HH" -> the archives that started in that hour, every
  // series together: one band for the repository, as the day view draws it
  const hours = useMemo(() => {
    const byHour = new Map<string, HourCell>()
    for (const archive of archives) {
      const at = parseBackendDate(archive.start)
      if (at < start) continue
      const key = `${format(at, 'yyyy-MM-dd')}:${at.getHours()}`
      const hour = byHour.get(key) ?? { archives: [] }
      hour.archives.push(archive)
      byHour.set(key, hour)
    }
    return byHour
  }, [archives, start])

  useEffect(() => {
    const node = scrollRef.current
    if (node) node.scrollLeft = node.scrollWidth
  }, [scrollRef, cell])

  const days = Array.from({ length: dayCount }, (_, i) => addDays(start, i))

  if (hours.size === 0) {
    return (
      <Stack spacing={2}>
        {header && (
          <HeatmapHeader
            toolbar={header.toolbar}
            summary={t('archives.hourly.none', { count: weeks })}
          />
        )}
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {t('archives.hourly.none', { count: weeks })}
        </Typography>
      </Stack>
    )
  }

  const activate = (target: HTMLElement, hour: HourCell) => {
    if (hour.archives.length === 1) onSelectArchive(hour.archives[0].id)
    else setChooser({ anchor: target, cell: hour })
  }

  return (
    <Stack spacing={2}>
      {header ? (
        <HeatmapHeader
          toolbar={header.toolbar}
          summary={t('archives.hourly.window', { count: weeks })}
        />
      ) : (
        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
          {t('archives.hourly.window', { count: weeks })}
        </Typography>
      )}
      <Box ref={scrollRef} sx={{ overflowX: 'auto', pb: 1, bgcolor: 'background.paper' }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-end', mb: 0.5 }}>
          <Box
            sx={{
              width: HOUR_WIDTH,
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
        <Box sx={{ display: 'flex', alignItems: 'flex-start' }}>
          {/* The hour axis stays put while the grid scrolls; scrolled
              away, the cells on screen would have no time to read. */}
          <Box
            sx={{
              width: HOUR_WIDTH,
              flexShrink: 0,
              position: 'sticky',
              left: 0,
              bgcolor: 'background.paper',
              zIndex: 1,
            }}
          >
            {Array.from({ length: HOURS }, (_, hour) => (
              <Typography
                key={hour}
                variant="caption"
                sx={{
                  display: 'block',
                  height: row,
                  lineHeight: `${row}px`,
                  mb: `${GAP}px`,
                  fontSize: row >= 16 ? 10 : 9,
                  color: 'text.secondary',
                  visibility: hour % 6 === 0 || row >= 16 ? 'visible' : 'hidden',
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
              gridTemplateRows: `repeat(${HOURS}, ${row}px)`,
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
                    data-testid={`hourly-cell-repository-${iso}-${hour}`}
                    data-count={count}
                    role={count > 0 ? 'button' : undefined}
                    tabIndex={count > 0 ? 0 : undefined}
                    onClick={entry ? (event) => activate(event.currentTarget, entry) : undefined}
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
                      height: row,
                      borderRadius: row >= 14 ? '4px' : '2px',
                      cursor: count > 0 ? 'pointer' : 'default',
                      bgcolor:
                        count > 0
                          ? alpha(theme.palette.primary.main, countScale(count))
                          : alpha(theme.palette.text.primary, hour % 6 === 0 ? 0.08 : 0.05),
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: Math.max(8, row - 6),
                      fontWeight: 700,
                      color: theme.palette.primary.contrastText,
                      '&:focus-visible': {
                        outline: `2px solid ${theme.palette.primary.main}`,
                        outlineOffset: 1,
                      },
                    }}
                  >
                    {row >= 14 && count > 1 ? count : null}
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
