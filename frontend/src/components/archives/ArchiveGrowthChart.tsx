import { useState } from 'react'
import {
  Box,
  Checkbox,
  FormControlLabel,
  Paper,
  Stack,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { useTranslation } from 'react-i18next'
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import RichSelect from '../shared/RichSelect'
import { formatBytes, formatDateCompact, formatDateShort } from '../../utils/dateUtils'
import type { GrowthPoint, GrowthResponse } from '../../types/archives'

export interface ArchiveGrowthChartProps {
  data: GrowthResponse
  // '' means every series (the whole repository).
  series: string
  onSeriesChange: (series: string) => void
  onSelectArchive: (archiveId: number) => void
}

const HEIGHT = 320
const STALE_OPACITY = 0.35
const MEASURED_OPACITY = 0.9

// Recharts hands the bar's data entry to onClick under `payload`.
type BarClick = { payload?: GrowthPoint }

interface TooltipProps {
  active?: boolean
  payload?: { payload: GrowthPoint }[]
  showSource: boolean
}

function GrowthTooltip({ active, payload, showSource }: TooltipProps) {
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
      {row(t('archives.growth.tooltipAdded'), formatBytes(point.deduplicated_size))}
      {row(t('archives.growth.tooltipFootprint'), formatBytes(point.running_total))}
      {showSource && row(t('archives.growth.tooltipSource'), formatBytes(point.original_size))}
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

export default function ArchiveGrowthChart({
  data,
  series,
  onSeriesChange,
  onSelectArchive,
}: ArchiveGrowthChartProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const [showSource, setShowSource] = useState(false)

  const barColor = theme.palette.primary.main
  // The dark info.main sits too close to the dark primary for two marks to
  // read apart (palette check 2026-09-17); the lighter step passes.
  const footprintColor =
    theme.palette.mode === 'dark' ? theme.palette.info.light : theme.palette.info.main
  const sourceColor = theme.palette.text.secondary
  const gridColor = alpha(theme.palette.text.primary, 0.08)
  const tickStyle = { fill: theme.palette.text.secondary, fontSize: 11 }

  const seriesOptions = [
    { value: '', primary: t('archives.growth.allSeries') },
    ...data.series.map((name) => ({ value: name, primary: name })),
  ]
  const hasSeriesChoice = data.series.length > 1
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
        {hasSeriesChoice && (
          <RichSelect
            value={series}
            onChange={onSeriesChange}
            options={seriesOptions}
            label={t('archives.growth.seriesLabel')}
            sx={{ minWidth: 200 }}
          />
        )}
        {enough && (
          <FormControlLabel
            control={
              <Checkbox
                size="small"
                checked={showSource}
                onChange={(event) => setShowSource(event.target.checked)}
              />
            }
            label={t('archives.growth.showSource')}
          />
        )}
      </Stack>

      {!enough ? (
        <Typography variant="body2" sx={{ color: 'text.secondary', py: 6, textAlign: 'center' }}>
          {t('archives.growth.empty')}
        </Typography>
      ) : (
        <>
          <ResponsiveContainer
            width="100%"
            height={HEIGHT}
            initialDimension={{ width: 800, height: HEIGHT }}
          >
            <ComposedChart data={data.points} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
              <CartesianGrid vertical={false} stroke={gridColor} />
              <XAxis
                dataKey="start"
                tickFormatter={(value: string) => formatDateShort(value)}
                minTickGap={40}
                tick={tickStyle}
                tickLine={false}
                axisLine={{ stroke: gridColor }}
              />
              <YAxis
                yAxisId="added"
                tickFormatter={(value: number) => formatBytes(value)}
                width={84}
                tick={tickStyle}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                yAxisId="total"
                orientation="right"
                tickFormatter={(value: number) => formatBytes(value)}
                width={84}
                tick={tickStyle}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                cursor={{ fill: alpha(theme.palette.text.primary, 0.06) }}
                content={<GrowthTooltip showSource={showSource} />}
              />
              <Bar
                yAxisId="added"
                dataKey="deduplicated_size"
                fill={barColor}
                radius={[2, 2, 0, 0]}
                maxBarSize={18}
                isAnimationActive={false}
                cursor="pointer"
                onClick={(entry: BarClick) => {
                  const id = entry.payload?.archive_id
                  if (id != null) onSelectArchive(id)
                }}
              >
                {data.points.map((point) => (
                  <Cell
                    key={point.archive_id}
                    fillOpacity={point.stale ? STALE_OPACITY : MEASURED_OPACITY}
                  />
                ))}
              </Bar>
              <Line
                yAxisId="total"
                type="monotone"
                dataKey="running_total"
                stroke={footprintColor}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
              {showSource && (
                <Line
                  yAxisId="total"
                  type="monotone"
                  dataKey="original_size"
                  stroke={sourceColor}
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                  dot={false}
                  activeDot={{ r: 3 }}
                  isAnimationActive={false}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>

          <Stack
            direction="row"
            spacing={2}
            useFlexGap
            sx={{ flexWrap: 'wrap', mt: 1.5, color: 'text.secondary', typography: 'caption' }}
          >
            <span>
              <Swatch color={barColor} opacity={MEASURED_OPACITY} />
              {t('archives.growth.legendAdded')}
            </span>
            <span>
              <Swatch color={footprintColor} line />
              {t('archives.growth.legendFootprint')}
            </span>
            {showSource && (
              <span>
                <Swatch color={sourceColor} line dashed />
                {t('archives.growth.legendSource')}
              </span>
            )}
            {data.stale_count > 0 && (
              <span>
                <Swatch color={barColor} opacity={STALE_OPACITY} />
                {t('archives.growth.legendStale')}
              </span>
            )}
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
