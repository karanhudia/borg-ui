import React from 'react'
import { Box, Stack, Tooltip, Typography, useTheme, alpha } from '@mui/material'
import { Archive as ArchiveIcon, Database } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatBytes as formatBytesUtil } from '../utils/dateUtils'

interface RepositoryStats {
  original_size: number
  compressed_size: number
  deduplicated_size: number
  total_files?: number
}

interface RepositoryStatsGridProps {
  stats: RepositoryStats
  archivesCount: number
  borgVersion?: number
}

type ColorKey = 'primary' | 'success' | 'info' | 'secondary' | 'warning'

interface StatCardProps {
  label: string
  value: string | number
  icon: React.ReactNode
  colorKey: ColorKey
  tooltip?: string
}

function StatCard({ label, value, icon, colorKey, tooltip }: StatCardProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const color = (theme.palette[colorKey] as { main: string }).main

  const card = (
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

  if (!tooltip) {
    return card
  }

  return (
    <Tooltip title={tooltip} arrow>
      {card}
    </Tooltip>
  )
}

export default function RepositoryStatsGrid({
  stats,
  archivesCount,
  borgVersion,
}: RepositoryStatsGridProps) {
  const { t } = useTranslation()
  const isBorg2 = borgVersion === 2

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(4, 1fr)' },
        gap: 2,
        mb: 0,
      }}
    >
      <StatCard
        label={t('repositoryStatsGrid.totalArchives')}
        value={archivesCount}
        icon={<ArchiveIcon size={32} />}
        colorKey="primary"
      />
      <StatCard
        label={t('repositoryStatsGrid.repositorySize')}
        value={formatBytesUtil(stats.deduplicated_size)}
        icon={<Database size={32} />}
        colorKey="success"
        tooltip={t('repositoryStatsGrid.repositorySizeTooltip')}
      />
      <StatCard
        label={t('repositoryStatsGrid.originalSize')}
        value={formatBytesUtil(stats.original_size)}
        icon={<Database size={32} />}
        colorKey="info"
        tooltip={t('repositoryStatsGrid.originalSizeTooltip')}
      />
      <StatCard
        label={
          isBorg2 ? t('repositoryStatsGrid.numberOfFiles') : t('repositoryStatsGrid.compressedSize')
        }
        value={isBorg2 ? stats.total_files || 0 : formatBytesUtil(stats.compressed_size)}
        icon={isBorg2 ? <ArchiveIcon size={32} /> : <Database size={32} />}
        colorKey="secondary"
        tooltip={
          isBorg2
            ? t('repositoryStatsGrid.numberOfFilesTooltip')
            : t('repositoryStatsGrid.compressedSizeTooltip')
        }
      />
    </Box>
  )
}
