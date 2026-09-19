import { Box, Paper, Stack, Typography, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatBytes, formatDateCompact, formatDateShort } from '../../utils/dateUtils'
import type { GrowthPoint, GrowthResponse } from '../../types/archives'

export interface ArchiveGrowthChartProps {
  data: GrowthResponse
  onSelectArchive: (archiveId: number) => void
}

const HEIGHT = 260

interface TooltipProps {
  active?: boolean
  payload?: { payload: GrowthPoint }[]
}

function GrowthTooltip({ active, payload }: TooltipProps) {
  const { t } = useTranslation()
  const point = payload?.[0]?.payload
  if (!active || !point) return null
  const row = (label: string, value: string) => (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2 }}>
      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
        {label}
      </Typography>
      <Typography variant="caption" sx={{ fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </Typography>
    </Box>
  )
  return (
    <Paper elevation={3} sx={{ p: 1.25, minWidth: 220 }}>
      <Typography variant="subtitle2" sx={{ wordBreak: 'break-all' }}>
        {point.name}
      </Typography>
      <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 0.5 }}>
        {formatDateCompact(point.start)}
      </Typography>
      {row(
        t('archives.growth.tooltipRepository'),
        point.repository_size != null ? formatBytes(point.repository_size) : '–'
      )}
      {row(
        t('archives.growth.tooltipSource'),
        point.original_size != null ? formatBytes(point.original_size) : '–'
      )}
      {row(t('archives.growth.tooltipAdded'), formatBytes(point.deduplicated_size))}
      {point.stale && (
        <Typography variant="caption" sx={{ color: 'warning.main', display: 'block', mt: 0.5 }}>
          {t('archives.growth.tooltipStale')}
        </Typography>
      )}
      <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mt: 0.5 }}>
        {t('archives.growth.openArchive')}
      </Typography>
    </Paper>
  )
}

function Swatch({
  color,
  line,
  dashed,
  opacity = 1,
}: {
  color: string
  line?: boolean
  dashed?: boolean
  opacity?: number
}) {
  return (
    <Box
      component="span"
      sx={{
        display: 'inline-block',
        width: 14,
        height: line ? 0 : 12,
        borderRadius: line ? 0 : 0.5,
        bgcolor: line ? 'transparent' : color,
        borderTop: line ? `2px ${dashed ? 'dashed' : 'solid'} ${color}` : 'none',
        opacity,
        mr: 0.75,
        verticalAlign: line ? 'middle' : '-2px',
      }}
    />
  )
}

export default function ArchiveGrowthChart({ data, onSelectArchive }: ArchiveGrowthChartProps) {
  const { t } = useTranslation()
  const theme = useTheme()

  // Two lines on one axis, in the tones the repository header uses for the
  // same figures: the repository's size after each backup in the amber of
  // "used on disk", filled beneath so growth reads as ground gained; the
  // source size dashed in the blue of "original size". What each archive
  // adds on its own is in the tooltip, where it does not fight the lines.
  const repositoryColor = theme.palette.warning.main
  const sourceColor = theme.palette.info.main
  const gridColor = alpha(theme.palette.text.primary, 0.08)
  const tick = { fill: theme.palette.text.secondary, fontSize: 11 }
  const dots = data.points.length <= 40

  const enough = data.points.length >= 2

  return (
    <Box data-testid="archive-growth-chart">
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        sx={{ alignItems: { xs: 'stretch', sm: 'center' }, mb: 2 }}
      >
        <Typography variant="subtitle1" sx={{ fontWeight: 600, flexGrow: 1 }}>
          {t('archives.growth.title')}
        </Typography>
      </Stack>

      {!enough ? (
        <Typography variant="body2" sx={{ color: 'text.secondary', py: 6, textAlign: 'center' }}>
          {t('archives.growth.empty')}
        </Typography>
      ) : (
        <>
          <Box
            sx={{
              // recharts makes the chart focusable for keyboard use; the ring
              // is for the keyboard, not for a click on a bar
              '& .recharts-wrapper:focus, & svg:focus': { outline: 'none' },
              '& .recharts-wrapper:focus-visible, & svg:focus-visible': {
                outline: `2px solid ${theme.palette.primary.main}`,
                outlineOffset: 2,
                borderRadius: 1,
              },
            }}
          >
            <ResponsiveContainer
              width="100%"
              height={HEIGHT}
              initialDimension={{ width: 800, height: HEIGHT }}
            >
              <ComposedChart
                data={data.points}
                margin={{ top: 12, right: 12, bottom: 0, left: 8 }}
                style={{ cursor: 'pointer' }}
                // a click anywhere in a column opens that archive
                onClick={(state) => {
                  const index = state?.activeTooltipIndex
                  const point = typeof index === 'number' ? data.points[index] : undefined
                  if (point) onSelectArchive(point.archive_id)
                }}
              >
                <defs>
                  <linearGradient id="growth-repository-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={repositoryColor} stopOpacity={0.28} />
                    <stop offset="100%" stopColor={repositoryColor} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke={gridColor} />
                <XAxis
                  dataKey="start"
                  tickFormatter={(value: string) => formatDateShort(value)}
                  minTickGap={40}
                  tick={tick}
                  tickLine={false}
                  axisLine={{ stroke: gridColor }}
                />
                <YAxis
                  tickFormatter={(value: number) => formatBytes(value)}
                  width={84}
                  tick={tick}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  cursor={{ stroke: alpha(theme.palette.text.primary, 0.2) }}
                  content={<GrowthTooltip />}
                />
                <Area
                  type="linear"
                  dataKey="repository_size"
                  stroke={repositoryColor}
                  strokeWidth={2.5}
                  fill="url(#growth-repository-fill)"
                  dot={dots ? { r: 3.5, fill: repositoryColor, strokeWidth: 0 } : false}
                  activeDot={{ r: 5 }}
                  isAnimationActive={false}
                  connectNulls
                />
                <Line
                  type="linear"
                  dataKey="original_size"
                  stroke={sourceColor}
                  strokeWidth={1.5}
                  strokeDasharray="5 4"
                  dot={dots ? { r: 3, fill: sourceColor, strokeWidth: 0 } : false}
                  activeDot={{ r: 5 }}
                  isAnimationActive={false}
                  connectNulls
                />
              </ComposedChart>
            </ResponsiveContainer>
          </Box>

          <Stack
            direction="row"
            spacing={2}
            useFlexGap
            sx={{ flexWrap: 'wrap', mt: 1.5, color: 'text.secondary', typography: 'caption' }}
          >
            <span>
              <Swatch color={repositoryColor} line />
              {t('archives.growth.legendRepository')}
            </span>
            <span>
              <Swatch color={sourceColor} line dashed />
              {t('archives.growth.legendSource')}
            </span>
          </Stack>

          {(data.stale_count > 0 || data.unmeasured_count > 0) && (
            <Box sx={{ mt: 1 }}>
              {data.stale_count > 0 && (
                <Typography variant="caption" sx={{ color: 'warning.main', display: 'block' }}>
                  {t('archives.growth.staleNote', { count: data.stale_count })}
                </Typography>
              )}
              {data.unmeasured_count > 0 && (
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                  {t('archives.growth.unmeasuredNote', { count: data.unmeasured_count })}
                </Typography>
              )}
            </Box>
          )}
        </>
      )}
    </Box>
  )
}
