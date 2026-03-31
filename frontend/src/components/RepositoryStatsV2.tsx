import { Box, Card, CardContent, Typography, Alert } from '@mui/material'
import { DataUsage, Inventory, Folder, Schedule } from '@mui/icons-material'
import { Info } from '@mui/icons-material'
import { useTranslation } from 'react-i18next'
import { formatBytes, formatDateShort } from '../utils/dateUtils'

export interface ArchiveEntry {
  name?: string
  time?: string
  stats?: {
    original_size?: number
    nfiles?: number
  }
}

interface RepositoryStatsV2Props {
  archives: ArchiveEntry[]
}

export default function RepositoryStatsV2({ archives }: RepositoryStatsV2Props) {
  const { t } = useTranslation()

  if (archives.length === 0) {
    return (
      <Alert severity="info" icon={<Info />}>
        <Typography variant="body2" fontWeight={600} gutterBottom>
          {t('dialogs.repositoryInfo.noBackupsYet')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('repositoryInfoDialog.noArchivesDescription')}
        </Typography>
      </Alert>
    )
  }

  const first = archives[0]
  const latest = archives[archives.length - 1]

  return (
    <>
      <Typography variant="h6" fontWeight={600} sx={{ mt: 1 }}>
        {t('dialogs.repositoryInfo.storageStatistics')}
      </Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 2 }}>
        <Card sx={{ backgroundColor: '#e8f5e9' }}>
          <CardContent sx={{ py: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <DataUsage sx={{ color: '#2e7d32', fontSize: 24 }} />
              <Typography variant="caption" color="text.secondary" fontWeight={500}>
                {t('dialogs.repositoryInfo.latestBackupSize')}
              </Typography>
            </Box>
            <Typography variant="h6" fontWeight={700} sx={{ color: '#2e7d32' }}>
              {formatBytes(latest.stats?.original_size || 0)}
            </Typography>
          </CardContent>
        </Card>
        <Card sx={{ backgroundColor: '#fff3e0' }}>
          <CardContent sx={{ py: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Inventory sx={{ color: '#e65100', fontSize: 24 }} />
              <Typography variant="caption" color="text.secondary" fontWeight={500}>
                {t('dialogs.repositoryInfo.files')}
              </Typography>
            </Box>
            <Typography variant="h6" fontWeight={700} sx={{ color: '#e65100' }}>
              {(latest.stats?.nfiles ?? 0).toLocaleString()}
            </Typography>
          </CardContent>
        </Card>
        <Card sx={{ backgroundColor: '#e3f2fd' }}>
          <CardContent sx={{ py: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Folder sx={{ color: '#1565c0', fontSize: 24 }} />
              <Typography variant="caption" color="text.secondary" fontWeight={500}>
                {t('dialogs.repositoryInfo.archiveCount')}
              </Typography>
            </Box>
            <Typography variant="h6" fontWeight={700} sx={{ color: '#1565c0' }}>
              {archives.length.toLocaleString()}
            </Typography>
          </CardContent>
        </Card>
      </Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 2 }}>
        <Card variant="outlined">
          <CardContent sx={{ py: 1.5 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <Schedule sx={{ color: 'text.secondary', fontSize: 18 }} />
              <Typography variant="caption" color="text.secondary" display="block">
                {t('dialogs.repositoryInfo.firstBackup')}
              </Typography>
            </Box>
            <Typography variant="body2" fontWeight={600}>
              {first.time ? formatDateShort(first.time) : t('common.na')}
            </Typography>
          </CardContent>
        </Card>
        <Card variant="outlined">
          <CardContent sx={{ py: 1.5 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <Schedule sx={{ color: 'text.secondary', fontSize: 18 }} />
              <Typography variant="caption" color="text.secondary" display="block">
                {t('dialogs.repositoryInfo.latestBackup')}
              </Typography>
            </Box>
            <Typography variant="body2" fontWeight={600}>
              {latest.time ? formatDateShort(latest.time) : t('common.na')}
            </Typography>
          </CardContent>
        </Card>
      </Box>
    </>
  )
}
