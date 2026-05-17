import { Box, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { addDays, differenceInDays, format, startOfDay } from 'date-fns'
import { JOB_COLOR, useT } from './tokens'
import type { DashboardOverview } from './types'

/**
 * Activity Timeline — SVG scatter plot
 * X axis: last 14 days
 * Y axis: time of day (0 – 24 h)
 * Each dot = one job event, colored by type; red border = failed
 */
export function ActivityTimeline({
  activities,
}: {
  activities: DashboardOverview['activity_feed']
}) {
  const T = useT()
  const { t } = useTranslation()
  const DAYS = 14
  const VB_W = 680,
    VB_H = 110
  const ML = 32,
    MR = 8,
    MT = 10,
    MB = 22
  const cW = VB_W - ML - MR // chart width
  const cH = VB_H - MT - MB // chart height
  const colW = cW / DAYS

  const today = startOfDay(new Date())

  // Map activities to (x, y) positions
  const dots = activities.flatMap((a) => {
    const date = new Date(a.timestamp)
    const dayAgo = differenceInDays(today, startOfDay(date))
    if (dayAgo >= DAYS || dayAgo < 0) return []
    const col = DAYS - 1 - dayAgo
    const x = ML + (col + 0.5) * colW
    const hourFrac = (date.getHours() * 60 + date.getMinutes()) / (24 * 60)
    const y = MT + hourFrac * cH
    const jobColor = a.status === 'failed' ? T.red : (JOB_COLOR[a.type] ?? T.textMuted)
    return [
      {
        x,
        y,
        color: jobColor,
        failed: a.status === 'failed',
        title: `${a.type} • ${a.repository} • ${format(date, 'HH:mm')}`,
      },
    ]
  })

  // Day column labels (show every 2nd to avoid crowding)
  const dayLabels = Array.from({ length: DAYS }, (_, i) => {
    const d = addDays(today, -(DAYS - 1 - i))
    return {
      x: ML + (i + 0.5) * colW,
      label: format(d, 'M/d'),
      show: i % 2 === 0 || i === DAYS - 1,
    }
  })

  // Hour guide lines
  const hours = [0, 6, 12, 18, 24]

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

        {/* Hour guide lines */}
        {hours.map((h) => {
          const y = MT + (h / 24) * cH
          return (
            <g key={h}>
              <line x1={ML} y1={y} x2={ML + cW} y2={y} stroke={T.svgTrack} strokeWidth={1} />
              {h < 24 && (
                <text
                  x={ML - 4}
                  y={y + 4}
                  fontSize={8}
                  fill={T.axisLabel}
                  textAnchor="end"
                  fontFamily="ui-monospace,monospace"
                >
                  {h}h
                </text>
              )}
            </g>
          )
        })}

        {/* Today highlight column */}
        <rect x={ML + (DAYS - 1) * colW} y={MT} width={colW} height={cH} fill={T.todayCol} rx={2} />

        {/* Activity dots */}
        {dots.map((d, i) => (
          <g key={i}>
            {/* Glow halo for failed */}
            {d.failed && <circle cx={d.x} cy={d.y} r={7} fill={d.color} opacity={0.2} />}
            <circle
              cx={d.x}
              cy={d.y}
              r={4}
              fill={d.color}
              stroke={d.failed ? 'rgba(255,255,255,0.4)' : 'none'}
              strokeWidth={d.failed ? 1 : 0}
              style={{ filter: `drop-shadow(0 0 4px ${d.color}90)` }}
            >
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
          y={MT - 4}
          fontSize={8}
          fill={T.indigo}
          textAnchor="middle"
          fontFamily="ui-monospace,monospace"
        >
          {t('dashboard.activityTimeline.today')}
        </text>
      </svg>

      {/* Legend */}
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
        {Object.entries(JOB_COLOR).map(([type, color]) => (
          <Stack key={type} direction="row" spacing={0.5} alignItems="center">
            <Box
              sx={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                bgcolor: color,
                boxShadow: `0 0 4px ${color}80`,
              }}
            />
            <Typography sx={{ fontFamily: T.mono, fontSize: '0.6rem', color: T.textMuted }}>
              {t(`dashboard.activityTimeline.jobType.${type}`, { defaultValue: type })}
            </Typography>
          </Stack>
        ))}
        <Stack direction="row" spacing={0.5} alignItems="center">
          <Box
            sx={{
              width: 7,
              height: 7,
              borderRadius: '50%',
              bgcolor: T.red,
              border: '1px solid rgba(255,255,255,0.4)',
            }}
          />
          <Typography sx={{ fontFamily: T.mono, fontSize: '0.6rem', color: T.textMuted }}>
            {t('dashboard.activityTimeline.legendFailed')}
          </Typography>
        </Stack>
      </Stack>
    </Box>
  )
}
