import { Box, Card, CardContent, Typography } from '@mui/material'
import { DataUsage, Compress, Inventory } from '@mui/icons-material'
import { useTranslation } from 'react-i18next'
import { formatBytes } from '../utils/dateUtils'

export interface CacheStats {
  total_size?: number
  unique_size?: number
  unique_csize?: number
  total_chunks?: number
  total_unique_chunks?: number
}

interface RepositoryStatsV1Props {
  stats: CacheStats
}

export default function RepositoryStatsV1({ stats }: RepositoryStatsV1Props) {
  const { t } = useTranslation()

  return (
    <>
      <Typography variant="h6" fontWeight={600} sx={{ mt: 1 }}>
        {t('dialogs.repositoryInfo.storageStatistics')}
      </Typography>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(3, 1fr)' },
          gap: 2,
        }}
      >
        <Card sx={{ backgroundColor: '#e8f5e9' }}>
          <CardContent sx={{ py: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <DataUsage sx={{ color: '#2e7d32', fontSize: 24 }} />
              <Typography variant="caption" color="text.secondary" fontWeight={500}>
                {t('dialogs.repositoryInfo.totalSize')}
              </Typography>
            </Box>
            <Typography variant="h6" fontWeight={700} sx={{ color: '#2e7d32' }}>
              {formatBytes(stats.total_size || 0)}
            </Typography>
          </CardContent>
        </Card>
        <Card sx={{ backgroundColor: '#e3f2fd' }}>
          <CardContent sx={{ py: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Compress sx={{ color: '#1565c0', fontSize: 24 }} />
              <Typography variant="caption" color="text.secondary" fontWeight={500}>
                {t('dialogs.repositoryInfo.usedOnDisk')}
              </Typography>
            </Box>
            <Typography variant="h6" fontWeight={700} sx={{ color: '#1565c0' }}>
              {formatBytes(stats.unique_csize || 0)}
            </Typography>
          </CardContent>
        </Card>
        <Card sx={{ backgroundColor: '#fff3e0' }}>
          <CardContent sx={{ py: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Inventory sx={{ color: '#e65100', fontSize: 24 }} />
              <Typography variant="caption" color="text.secondary" fontWeight={500}>
                {t('dialogs.repositoryInfo.uniqueData')}
              </Typography>
            </Box>
            <Typography variant="h6" fontWeight={700} sx={{ color: '#e65100' }}>
              {formatBytes(stats.unique_size || 0)}
            </Typography>
          </CardContent>
        </Card>
      </Box>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)' },
          gap: 2,
        }}
      >
        <Card variant="outlined">
          <CardContent sx={{ py: 1.5 }}>
            <Typography variant="caption" color="text.secondary" display="block">
              {t('dialogs.repositoryInfo.totalChunks')}
            </Typography>
            <Typography variant="h6" fontWeight={600}>
              {stats.total_chunks?.toLocaleString()}
            </Typography>
          </CardContent>
        </Card>
        <Card variant="outlined">
          <CardContent sx={{ py: 1.5 }}>
            <Typography variant="caption" color="text.secondary" display="block">
              {t('dialogs.repositoryInfo.uniqueChunks')}
            </Typography>
            <Typography variant="h6" fontWeight={600}>
              {stats.total_unique_chunks?.toLocaleString()}
            </Typography>
          </CardContent>
        </Card>
      </Box>
    </>
  )
}
