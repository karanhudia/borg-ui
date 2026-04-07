import { Box, Card, CardContent, Stack, Typography } from '@mui/material'
import { alpha } from '@mui/material/styles'
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
  return (
    <Card
      variant="outlined"
      sx={{
        borderTopWidth: '3px',
        borderTopColor: `${colorKey}.main`,
        bgcolor: (theme) =>
          alpha(
            (theme.palette[colorKey] as { main: string }).main,
            theme.palette.mode === 'dark' ? 0.1 : 0.06
          ),
        transition: 'box-shadow 0.2s ease',
        '&:hover': { boxShadow: 3 },
      }}
    >
      <CardContent sx={{ pb: '16px !important' }}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
          <Box>
            <Typography
              variant="caption"
              sx={{
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                fontSize: '0.65rem',
                fontWeight: 700,
                color: `${colorKey}.main`,
                display: 'block',
                mb: 0.75,
              }}
            >
              {label}
            </Typography>
            <Typography
              variant="h5"
              fontWeight={700}
              color="text.primary"
              sx={{ lineHeight: 1.2, fontSize: { xs: '1.4rem', lg: '1.5rem' } }}
            >
              {value}
            </Typography>
          </Box>
          <Box
            sx={{
              color: `${colorKey}.main`,
              opacity: 0.35,
              mt: 0.25,
              flexShrink: 0,
            }}
          >
            {icon}
          </Box>
        </Stack>
      </CardContent>
    </Card>
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
