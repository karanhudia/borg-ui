import { Box } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { addDays, differenceInDays, format, parseISO, startOfDay } from 'date-fns'
import { JOB_COLOR, useT } from './tokens'
import type { DashboardOverview } from './types'

// Dots drawn per day column and lane. A busy day spreads more runs than a
// column can show apart, so the count caps the dots and the title says the
// real numbers.
const MAX_DOTS_PER_CELL = 5

/**
 * Activity Timeline. SVG lane chart.
 * X axis: last 14 days.
 * Y axis: job type rows (backup, check, compact, restore, prune).
 * Each cell is one day of one job type: a dot per run up to a cap, colored
 * by type; a red ring marks a failed run. The counts come per day from the
 * server, bucketed in the viewer's time zone. Time of day is intentionally
 * not encoded here; see the Full Log link in the panel header for that
 * level of detail.
 */
export function ActivityTimeline({
  timeline,
}: {
  timeline: NonNullable<DashboardOverview['activity_timeline']>
}) {
  const T = useT()
  const { t } = useTranslation()
  const DAYS = 14

  // Lane order: most important to least important for a backup tool.
  // backup first (the primary action), then check (integrity), compact
  // (housekeeping), restore (verification), prune (retention).
  const LANES: Array<keyof typeof JOB_COLOR | string> = [
    'backup',
    'check',
    'compact',
    'restore',
    'prune',
  ]
  // The API reports restore verification runs as "restore_check"; they
  // belong on the restore lane.
  const laneKey = (type: string) => (type === 'restore_check' ? 'restore' : type)
  const laneIndex = (type: string) => LANES.indexOf(laneKey(type))

  const VB_W = 680
  const ML = 44
  const MR = 8
  const MT = 6
  const MB = 18
  const LANE_H = 14
  const VB_H = MT + LANES.length * LANE_H + MB
  const cW = VB_W - ML - MR
  const cH = LANES.length * LANE_H
  const colW = cW / DAYS

  const today = startOfDay(new Date())

  // One cell per (day column, lane), summed over the entries that land on
  // it. A day after the viewer's today (the server fell back to UTC for a
  // zone it does not know, and the viewer is west of it) lands in the today
  // column rather than vanishing.
  type Cell = { col: number; lane: number; type: string; total: number; failed: number }
  const cells = new Map<string, Cell>()
  for (const entry of timeline) {
    const day = startOfDay(parseISO(entry.date))
    if (Number.isNaN(day.getTime())) continue
    const dayAgo = differenceInDays(today, day)
    if (dayAgo >= DAYS) continue
    const lane = laneIndex(entry.type)
    if (lane < 0) continue
    const col = DAYS - 1 - Math.max(0, dayAgo)
    const key = `${col}:${lane}`
    const cell = cells.get(key) ?? { col, lane, type: entry.type, total: 0, failed: 0 }
    cell.total += entry.total
    cell.failed += entry.failed
    cells.set(key, cell)
  }

  // The dots inside a cell are spread horizontally, capped so a busy day
  // still reads as one column. Failed runs take the rightmost dots.
  type Dot = {
    x: number
    y: number
    color: string
    failed: boolean
    title: string
  }
  const dots: Dot[] = []
  for (const cell of cells.values()) {
    const cx = ML + (cell.col + 0.5) * colW
    const cy = MT + (cell.lane + 0.5) * LANE_H
    const n = Math.min(cell.total, MAX_DOTS_PER_CELL)
    const failedDots = Math.min(cell.failed, n)
    // Keep dots fully inside the column by clamping the spread to about 60%
    // of column width.
    const spreadW = Math.min(colW * 0.6, 14)
    const title = t('dashboard.activityTimeline.cellTitle', {
      type: t(`dashboard.activityTimeline.jobType.${cell.type}`, {
        defaultValue: cell.type,
      }),
      count: cell.total,
      failed: cell.failed,
    })
    for (let i = 0; i < n; i++) {
      const failed = i >= n - failedDots
      const offset = n === 1 ? 0 : (i / (n - 1) - 0.5) * spreadW
      dots.push({
        x: cx + offset,
        y: cy,
        color: failed ? T.red : (JOB_COLOR[laneKey(cell.type)] ?? T.textMuted),
        failed,
        title,
      })
    }
  }

  // Day column labels (show every 2nd to avoid crowding, plus the last).
  const dayLabels = Array.from({ length: DAYS }, (_, i) => {
    const d = addDays(today, -(DAYS - 1 - i))
    return {
      x: ML + (i + 0.5) * colW,
      label: format(d, 'M/d'),
      show: i % 2 === 0 || i === DAYS - 1,
    }
  })

  return (
    <Box>
      <svg
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        style={{ width: '100%', height: 'auto', overflow: 'visible' }}
        aria-label={t('dashboard.activityTimeline.ariaLabel')}
      >
        {/* Alternating column shading */}
        {dayLabels.map(({ x }, i) =>
          i % 2 === 0 ? (
            <rect key={i} x={x - colW / 2} y={MT} width={colW} height={cH} fill={T.colShade} />
          ) : null
        )}

        {/* Today highlight column */}
        <rect x={ML + (DAYS - 1) * colW} y={MT} width={colW} height={cH} fill={T.todayCol} rx={2} />

        {/* Lane tracks and labels */}
        {LANES.map((type, i) => {
          const y = MT + (i + 0.5) * LANE_H
          return (
            <g key={type}>
              <line
                x1={ML}
                y1={y}
                x2={ML + cW}
                y2={y}
                stroke={T.svgTrack}
                strokeWidth={1}
                opacity={0.6}
              />
              <text
                x={ML - 4}
                y={y + 3}
                fontSize={8}
                fill={T.textMuted}
                textAnchor="end"
                fontFamily="ui-monospace,monospace"
              >
                {t(`dashboard.activityTimeline.jobType.${type}`, {
                  defaultValue: type.charAt(0).toUpperCase() + type.slice(1),
                })}
              </text>
            </g>
          )
        })}

        {/* Activity dots. Failed jobs use a larger ring so they read as
            distinct without depending on glow or shadow effects. */}
        {dots.map((d, i) => (
          <g key={i}>
            {d.failed && (
              <circle
                cx={d.x}
                cy={d.y}
                r={5.5}
                fill="none"
                stroke={d.color}
                strokeWidth={1.5}
                opacity={0.55}
              />
            )}
            <circle cx={d.x} cy={d.y} r={d.failed ? 3 : 3.25} fill={d.color}>
              <title>{d.title}</title>
            </circle>
          </g>
        ))}

        {/* Day labels */}
        {dayLabels.map(({ x, label, show }, i) =>
          show ? (
            <text
              key={i}
              x={x}
              y={VB_H - 4}
              fontSize={8}
              fill={T.axisLabel}
              textAnchor="middle"
              fontFamily="ui-monospace,monospace"
            >
              {label}
            </text>
          ) : null
        )}

        {/* "Today" label */}
        <text
          x={ML + (DAYS - 0.5) * colW}
          y={MT - 1}
          fontSize={8}
          fill={T.indigo}
          textAnchor="middle"
          fontFamily="ui-monospace,monospace"
        >
          {t('dashboard.activityTimeline.today')}
        </text>
      </svg>
    </Box>
  )
}
