import { Box, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { addDays, differenceInDays, format, startOfDay } from 'date-fns'
import { JOB_COLOR, useT } from './tokens'
import type { DashboardOverview } from './types'

/**
 * Activity Timeline. SVG lane chart.
 * X axis: last 14 days.
 * Y axis: job type rows (backup, check, compact, restore, prune).
 * Each dot is one job event, colored by type; a red ring marks failed.
 * Time of day is intentionally not encoded here; see the Full Log link
 * in the panel header for that level of detail.
 */
export function ActivityTimeline({
  activities,
}: {
  activities: DashboardOverview['activity_feed']
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
  const laneIndex = (type: string) => LANES.indexOf(type)

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

  // Group activities by (day column, lane) so multiple events in the same
  // cell can be spread horizontally within the day column. The spread is
  // deterministic (input order, capped to a small max) so repeated renders
  // look identical.
  type Dot = {
    x: number
    y: number
    color: string
    failed: boolean
    title: string
  }
  type CellKey = string
  const cells = new Map<CellKey, typeof activities>()
  for (const a of activities) {
    const date = new Date(a.timestamp)
    const dayAgo = differenceInDays(today, startOfDay(date))
    if (dayAgo >= DAYS || dayAgo < 0) continue
    const lane = laneIndex(a.type)
    if (lane < 0) continue
    const col = DAYS - 1 - dayAgo
    const key = `${col}:${lane}`
    const bucket = cells.get(key)
    if (bucket) bucket.push(a)
    else cells.set(key, [a])
  }

  const dots: Dot[] = []
  cells.forEach((bucket, key) => {
    const [colStr, laneStr] = key.split(':')
    const col = Number(colStr)
    const lane = Number(laneStr)
    const cx = ML + (col + 0.5) * colW
    const cy = MT + (lane + 0.5) * LANE_H
    const n = bucket.length
    // Horizontal spread inside the day column. Keep dots fully inside the
    // column by clamping the spread to about 60% of column width.
    const spreadW = Math.min(colW * 0.6, 14)
    for (let i = 0; i < n; i++) {
      const date = new Date(bucket[i].timestamp)
      const offset = n === 1 ? 0 : (i / (n - 1) - 0.5) * spreadW
      const jobColor =
        bucket[i].status === 'failed' ? T.red : (JOB_COLOR[bucket[i].type] ?? T.textMuted)
      dots.push({
        x: cx + offset,
        y: cy,
        color: jobColor,
        failed: bucket[i].status === 'failed',
        title: `${bucket[i].type} · ${bucket[i].repository} · ${format(date, 'HH:mm')}`,
      })
    }
  })

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

      {/* Compact legend: only the failed marker remains, since lane labels
          are now part of the chart itself. */}
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
        <Stack direction="row" spacing={0.65} alignItems="center">
          <Box
            sx={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              border: `1.5px solid ${T.red}`,
              flexShrink: 0,
            }}
          />
          <Typography sx={{ fontFamily: T.mono, fontSize: '0.75rem', color: T.textMuted }}>
            {t('dashboard.activityTimeline.legendFailed')}
          </Typography>
        </Stack>
      </Stack>
    </Box>
  )
}
