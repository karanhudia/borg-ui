import { Box, Card, CardContent, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { formatBytes, formatDurationSeconds, parseBackendDate } from '../../utils/dateUtils'
import type { ArchiveDetailResponse } from '../../types/archives'

interface ArchiveInfoTabProps {
  archive: ArchiveDetailResponse
}

function Field({ label, value }: { label: string; value: string | number | null }) {
  if (value === null || value === undefined || value === '') return null
  return (
    <Box sx={{ flex: '1 1 200px' }}>
      <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>
        {label}
      </Typography>
      <Typography variant="body1">{value}</Typography>
    </Box>
  )
}

export default function ArchiveInfoTab({ archive }: ArchiveInfoTabProps) {
  const { t } = useTranslation()

  return (
    <Card>
      <CardContent sx={{ py: 2 }}>
        <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
          <Field label={t('archives.detail.series')} value={archive.series} />
          <Field
            label={t('archives.detail.started')}
            value={parseBackendDate(archive.start).toLocaleString()}
          />
          <Field
            label={t('archives.detail.duration')}
            value={formatDurationSeconds(archive.duration_seconds)}
          />
          <Field label={t('archives.detail.files')} value={archive.nfiles} />
          <Field
            label={t('archives.detail.originalSize')}
            value={formatBytes(archive.original_size)}
          />
          <Field
            label={t('archives.detail.compressedSize')}
            value={formatBytes(archive.compressed_size)}
          />
          <Field
            label={t('archives.detail.deduplicatedSize')}
            value={formatBytes(archive.deduplicated_size)}
          />
          <Field label={t('archives.detail.hostname')} value={archive.hostname} />
          <Field label={t('archives.detail.username')} value={archive.username} />
          <Field label={t('archives.detail.comment')} value={archive.comment} />
        </Box>
      </CardContent>
    </Card>
  )
}
