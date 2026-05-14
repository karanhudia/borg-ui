import { Box, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { SEG_COLORS, useT } from './tokens'

export function SuccessDonut({ rate, good, total }: { rate: number; good: number; total: number }) {
  const T = useT()
  const size = 148,
    sw = 13,
    r = (size - sw) / 2
  const circ = 2 * Math.PI * r
  const filled = (rate / 100) * circ
  const color = rate >= 90 ? T.green : rate >= 70 ? T.amber : T.red
  return (
    <Box sx={{ position: 'relative', width: size, height: size, mx: 'auto' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={T.svgTrack}
          strokeWidth={sw}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={sw}
          strokeDasharray={`${filled} ${circ}`}
          strokeLinecap="round"
          style={{
            filter: `drop-shadow(0 0 8px ${color}80)`,
            transition: 'stroke-dasharray 0.8s cubic-bezier(0.4,0,0.2,1)',
          }}
        />
      </svg>
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Typography
          sx={{ fontFamily: T.mono, fontSize: '1.75rem', fontWeight: 700, color, lineHeight: 1 }}
        >
          {rate.toFixed(0)}%
        </Typography>
        <Typography sx={{ fontSize: '0.6rem', color: T.textMuted, mt: 0.5, letterSpacing: 1 }}>
          {good}/{total} OK
        </Typography>
      </Box>
    </Box>
  )
}

export function StorageDonut({
  breakdown,
  totalSize,
  totalArchives,
}: {
  breakdown: Array<{ name: string; size: string; size_bytes: number; percentage: number }>
  totalSize: string
  totalArchives: number
}) {
  const T = useT()
  const { t } = useTranslation()
  const size = 148,
    sw = 16,
    r = (size - sw) / 2
  const circ = 2 * Math.PI * r
  const slices = breakdown.slice(0, 5)
  const segments = slices.reduce<
    Array<{
      s: (typeof slices)[number]
      arc: number
      offset: number
      color: string
    }>
  >((acc, s, i) => {
    const previous = acc[acc.length - 1]
    const arc = (s.percentage / 100) * circ
    acc.push({
      s,
      arc,
      offset: previous ? previous.offset + previous.arc : 0,
      color: SEG_COLORS[i],
    })
    return acc
  }, [])

  return (
    <Box>
      <Box sx={{ position: 'relative', width: size, height: size, mx: 'auto' }}>
        <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={T.svgTrack}
            strokeWidth={sw}
          />
          {segments.map((seg, i) => (
            <circle
              key={i}
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={seg.color}
              strokeWidth={sw}
              strokeDasharray={`${Math.max(seg.arc - 2, 0)} ${circ}`}
              strokeDashoffset={-seg.offset}
              strokeLinecap="butt"
              style={{
                filter: `drop-shadow(0 0 6px ${seg.color}70)`,
                transition: 'stroke-dasharray 0.8s cubic-bezier(0.4,0,0.2,1)',
              }}
            />
          ))}
        </svg>
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Typography
            sx={{
              fontFamily: T.mono,
              fontSize: '1.05rem',
              fontWeight: 800,
              color: T.textPrimary,
              lineHeight: 1,
            }}
          >
            {totalSize}
          </Typography>
          <Typography
            sx={{
              fontSize: '0.55rem',
              color: T.textMuted,
              mt: 0.5,
              letterSpacing: 1.5,
              textTransform: 'uppercase',
            }}
          >
            {t('dashboard.storageDonut.archivesCount', { count: totalArchives })}
          </Typography>
        </Box>
      </Box>
      <Box sx={{ mt: 1.5, display: 'flex', flexDirection: 'column', gap: 0.65 }}>
        {slices.map((s, i) => (
          <Stack key={s.name} direction="row" alignItems="center" spacing={0.75}>
            <Box
              sx={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                bgcolor: SEG_COLORS[i],
                boxShadow: `0 0 4px ${SEG_COLORS[i]}80`,
                flexShrink: 0,
              }}
            />
            <Typography
              sx={{
                fontSize: '0.65rem',
                color: T.textMuted,
                flex: 1,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {s.name}
            </Typography>
            <Typography
              sx={{ fontFamily: T.mono, fontSize: '0.65rem', color: T.textPrimary, flexShrink: 0 }}
            >
              {s.percentage}%
            </Typography>
          </Stack>
        ))}
        {slices.length === 0 && (
          <Typography sx={{ fontSize: '0.7rem', color: T.textMuted, textAlign: 'center', py: 1 }}>
            {t('dashboard.storageDonut.noData')}
          </Typography>
        )}
      </Box>
    </Box>
  )
}

export function ArcGauge({
  value,
  color,
  label,
  sub,
}: {
  value: number
  color: string
  label: string
  sub?: string
}) {
  const T = useT()
  const size = 52,
    sw = 5,
    r = (size - sw) / 2
  const circ = 2 * Math.PI * r
  const filled = (Math.min(value, 100) / 100) * circ
  return (
    <Box sx={{ textAlign: 'center' }}>
      <Box sx={{ position: 'relative', width: size, height: size, mx: 'auto' }}>
        <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={T.svgTrack}
            strokeWidth={sw}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={sw}
            strokeDasharray={`${filled} ${circ}`}
            strokeLinecap="round"
            style={{
              filter: `drop-shadow(0 0 4px ${color}60)`,
              transition: 'stroke-dasharray 0.7s ease',
            }}
          />
        </svg>
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Typography
            sx={{ fontFamily: T.mono, fontSize: '0.62rem', fontWeight: 700, color: T.textPrimary }}
          >
            {value.toFixed(0)}%
          </Typography>
        </Box>
      </Box>
      <Typography sx={{ fontSize: '0.62rem', fontWeight: 600, color: T.textMuted, mt: 0.5 }}>
        {label}
      </Typography>
      {sub && (
        <Typography sx={{ fontSize: '0.58rem', color: T.textDim, mt: 0.15 }}>{sub}</Typography>
      )}
    </Box>
  )
}
