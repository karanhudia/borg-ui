import { Box, Typography, Button, alpha, useTheme } from '@mui/material'
import { RotateCcw, ExternalLink } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import RestoreJobCard from './RestoreJobCard'

interface RestoreJob {
  id: number
  repository: string
  archive: string
  destination: string
  status: string
  started_at?: string
  completed_at?: string
  progress?: number
  error_message?: string
  progress_details?: {
    nfiles: number
    current_file: string
    progress_percent: number
    restore_speed: number
    estimated_time_remaining: number
  }
}

interface LastRestoreSectionProps {
  restoreJob: RestoreJob | null
}

export default function LastRestoreSection({ restoreJob }: LastRestoreSectionProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  if (!restoreJob) {
    return (
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
        }}
      >
        <RotateCcw size={14} color={isDark ? alpha('#fff', 0.25) : alpha('#000', 0.25)} />
        <Typography variant="body2" color="text.disabled" sx={{ fontSize: '0.78rem' }}>
          {t('lastRestoreSection.noRestores')}
        </Typography>
      </Box>
    )
  }

  return (
    <Box>
      {/* Header row */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          mb: 1.25,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <RotateCcw size={15} color={theme.palette.secondary.main} />
          <Typography variant="body2" fontWeight={600} sx={{ fontSize: '0.82rem' }}>
            {t('lastRestoreSection.title')}
          </Typography>
        </Box>
        <Button
          variant="outlined"
          size="small"
          startIcon={<ExternalLink size={13} />}
          onClick={() => navigate('/activity')}
          sx={{
            textTransform: 'none',
            fontSize: '0.72rem',
            fontWeight: 500,
            height: 28,
            borderRadius: 1.5,
            px: 1.25,
            borderColor: isDark ? alpha('#fff', 0.12) : alpha('#000', 0.12),
            color: 'text.secondary',
            '&:hover': {
              borderColor: isDark ? alpha('#fff', 0.25) : alpha('#000', 0.2),
              bgcolor: isDark ? alpha('#fff', 0.04) : alpha('#000', 0.03),
            },
          }}
        >
          {t('lastRestoreSection.viewAll')}
        </Button>
      </Box>

      <RestoreJobCard job={restoreJob} showJobId={false} />
    </Box>
  )
}
