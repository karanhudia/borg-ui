import { Box, Stack, Typography, useTheme, alpha } from '@mui/material'
import { Archive as ArchiveIcon, Database, Gauge, Layers } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatBytes as formatBytesUtil } from '../utils/dateUtils'

interface RepositoryStats {
  unique_csize: number
  unique_size: number
  total_size: number
}

interface RepositoryStatsGridProps {
  stats: RepositoryStats
  archivesCount: number
}

type ColorKey = 'primary' | 'success' | 'info' | 'secondary' | 'warning'

interface StatCardProps {
  label: string
  value: string | number
  icon: React.ReactNode
  colorKey: ColorKey
}

function StatCard({ label, value, icon, colorKey }: StatCardProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const color = (theme.palette[colorKey] as { main: string }).main

  return (
    <Box
      sx={{
        borderRadius: 2,
        bgcolor: alpha(color, isDark ? 0.1 : 0.07),
        px: 2,
        py: 1.75,
        boxShadow: isDark
          ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 2px 8px ${alpha('#000', 0.2)}`
          : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 6px ${alpha('#000', 0.06)}`,
        transition: 'all 200ms cubic-bezier(0.16,1,0.3,1)',
        '&:hover': {
          transform: 'translateY(-1px)',
          boxShadow: isDark
            ? `0 0 0 1px ${alpha(color, 0.35)}, 0 6px 20px ${alpha('#000', 0.28)}`
            : `0 0 0 1px ${alpha(color, 0.25)}, 0 6px 20px ${alpha('#000', 0.1)}`,
        },
      }}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
        <Box>
          <Typography
            variant="caption"
            sx={{
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              fontSize: '0.6rem',
              fontWeight: 700,
              color,
              display: 'block',
              mb: 0.75,
            }}
          >
            {label}
          </Typography>
          <Typography
            variant="h5"
            fontWeight={700}
            sx={{ lineHeight: 1.2, fontSize: { xs: '1.4rem', lg: '1.5rem' }, color }}
          >
            {value}
          </Typography>
        </Box>
        <Box sx={{ color, opacity: 0.4, mt: 0.25, flexShrink: 0 }}>{icon}</Box>
      </Stack>
    </Box>
  )
}

export default function RepositoryStatsGrid({ stats, archivesCount }: RepositoryStatsGridProps) {
  const { t } = useTranslation()
  const spaceSaved = (stats.total_size || 0) - (stats.unique_csize || 0)
  const compressionRatio =
    stats.unique_size > 0 ? ((1 - stats.unique_csize / stats.unique_size) * 100).toFixed(1) : '0'
  const deduplicationRatio =
    stats.total_size > 0 ? ((1 - stats.unique_size / stats.total_size) * 100).toFixed(1) : '0'

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(5, 1fr)' },
        gap: 2,
        mb: 4,
      }}
    >
      <StatCard
        label={t('repositoryStatsGrid.totalArchives')}
        value={archivesCount}
        icon={<ArchiveIcon size={32} />}
        colorKey="primary"
      />
      <StatCard
        label={t('repositoryStatsGrid.spaceUsed')}
        value={formatBytesUtil(stats.unique_csize)}
        icon={<Database size={32} />}
        colorKey="success"
      />
      <StatCard
        label={t('repositoryStatsGrid.spaceSaved')}
        value={spaceSaved > 0 ? formatBytesUtil(spaceSaved) : '0 B'}
        icon={<Database size={32} />}
        colorKey="info"
      />
      <StatCard
        label={t('repositoryStatsGrid.compression')}
        value={`${compressionRatio}%`}
        icon={<Gauge size={32} />}
        colorKey="secondary"
      />
      <StatCard
        label={t('repositoryStatsGrid.deduplication')}
        value={`${deduplicationRatio}%`}
        icon={<Layers size={32} />}
        colorKey="warning"
      />
    </Box>
  )
}
