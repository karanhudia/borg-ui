import { Box, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { formatBytes, formatDurationSeconds, parseBackendDate } from '../../utils/dateUtils'
import type { ArchiveDetailResponse } from '../../types/archives'

interface ArchiveInfoTabProps {
  archive: ArchiveDetailResponse
}

function Field({
  label,
  value,
  span,
}: {
  label: string
  value: string | number | null
  span?: boolean
}) {
  if (value === null || value === undefined || value === '') return null
  return (
    <Box sx={{ minWidth: 0, gridColumn: span ? '1 / -1' : 'auto' }}>
      <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 0.25 }}>
        {label}
      </Typography>
      <Typography
        variant="body1"
        sx={{ wordBreak: 'break-word', fontVariantNumeric: 'tabular-nums' }}
      >
        {value}
      </Typography>
    </Box>
  )
}

export default function ArchiveInfoTab({ archive }: ArchiveInfoTabProps) {
  const { t } = useTranslation()

  const group = (children: React.ReactNode) => (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: {
          xs: '1fr',
          sm: 'repeat(2, minmax(0, 1fr))',
          md: 'repeat(4, minmax(0, 1fr))',
        },
        gap: 3,
        py: 2.5,
        '& + &': { borderTop: 1, borderColor: 'divider' },
      }}
    >
      {children}
    </Box>
  )

  return (
    <Box
      sx={{
        border: 1,
        borderColor: 'divider',
        borderRadius: 2,
        bgcolor: 'background.paper',
        px: 3,
      }}
    >
      {group(
        <>
          <Field label={t('archives.detail.series')} value={archive.series} span />
          <Field
            label={t('archives.detail.started')}
            value={parseBackendDate(archive.start).toLocaleString()}
          />
          <Field
            label={t('archives.detail.duration')}
            value={formatDurationSeconds(archive.duration_seconds)}
          />
          <Field
            label={t('archives.detail.files')}
            value={archive.nfiles?.toLocaleString() ?? null}
          />
          <Field label={t('archives.detail.hostname')} value={archive.hostname} />
        </>
      )}
      {group(
        <>
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
          <Field label={t('archives.detail.username')} value={archive.username} />
        </>
      )}
      {archive.comment &&
        group(<Field label={t('archives.detail.comment')} value={archive.comment} span />)}
    </Box>
  )
}
