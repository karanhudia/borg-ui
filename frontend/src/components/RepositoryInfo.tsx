import { Card, CardContent, Typography, Box, Chip } from '@mui/material'
import { Database, Archive, HardDrive, Calendar } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatBytes, formatDate } from '../utils/dateUtils'

interface RepositoryInfoProps {
  repoInfo?: {
    repository?: {
      id?: string
      last_modified?: string
    }
    cache?: {
      stats?: {
        total_size?: number
        total_csize?: number
        unique_csize?: number
        total_chunks?: number
        total_unique_chunks?: number
      }
    }
    encryption?: {
      mode?: string
    }
  }
  archivesCount?: number
  loading?: boolean
}

export default function RepositoryInfo({
  repoInfo,
  archivesCount = 0,
  loading = false,
}: RepositoryInfoProps) {
  const { t } = useTranslation()
  const stats = repoInfo?.cache?.stats

  if (loading) {
    return (
      <Card>
        <CardContent>
          <Typography variant="body2" color="text.secondary">
            {t('dialogs.repositoryInfo.loadingInfo')}
          </Typography>
        </CardContent>
      </Card>
    )
  }

  if (!repoInfo) {
    return null
  }

  return (
    <Card>
      <CardContent sx={{ py: 2 }}>
        <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
          <Box sx={{ flex: '1 1 200px' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <Archive size={16} color="#666" />
              <Typography variant="caption" color="text.secondary" fontWeight={600}>
                {t('repositoryInfo.archives')}
              </Typography>
            </Box>
            <Typography variant="h6" fontWeight={600}>
              {archivesCount}
            </Typography>
          </Box>

          <Box sx={{ flex: '1 1 200px' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <HardDrive size={16} color="#666" />
              <Typography variant="caption" color="text.secondary" fontWeight={600}>
                {t('repositoryInfo.totalSize')}
              </Typography>
            </Box>
            <Typography variant="h6" fontWeight={600}>
              {stats?.total_size ? formatBytes(stats.total_size) : t('repositoryInfo.na')}
            </Typography>
          </Box>

          <Box sx={{ flex: '1 1 200px' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <Database size={16} color="#666" />
              <Typography variant="caption" color="text.secondary" fontWeight={600}>
                {t('dialogs.repositoryInfo.uniqueData')}
              </Typography>
            </Box>
            <Typography variant="h6" fontWeight={600}>
              {stats?.unique_csize ? formatBytes(stats.unique_csize) : t('repositoryInfo.na')}
            </Typography>
          </Box>

          <Box sx={{ flex: '1 1 200px' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <Calendar size={16} color="#666" />
              <Typography variant="caption" color="text.secondary" fontWeight={600}>
                {t('repositoryInfo.lastModified')}
              </Typography>
            </Box>
            <Typography variant="body2" fontWeight={600}>
              {repoInfo.repository?.last_modified
                ? formatDate(repoInfo.repository.last_modified)
                : t('repositoryInfo.na')}
            </Typography>
          </Box>
        </Box>

        {repoInfo.encryption?.mode && (
          <Box sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: 'divider' }}>
            <Chip
              label={`${t('repositoryInfo.encryption')}: ${repoInfo.encryption.mode}`}
              size="small"
              color="primary"
              variant="outlined"
            />
          </Box>
        )}
      </CardContent>
    </Card>
  )
}
