import { Box, Stack, Typography, Button, alpha, useTheme } from '@mui/material'
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

  const cardSx = {
    px: 0,
    py: 0,
  }

  if (!restoreJob) {
    return (
      <Box sx={{ ...cardSx, mb: 4 }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <RotateCcw size={18} color={isDark ? alpha('#fff', 0.3) : alpha('#000', 0.3)} />
          <Typography variant="body2" color="text.disabled">
            {t('lastRestoreSection.noRestores')}
          </Typography>
        </Stack>
      </Box>
    )
  }

  return (
    <Box>
      <Stack
        direction="row"
        spacing={1.5}
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 1.5 }}
      >
        <Stack direction="row" spacing={1.5} alignItems="center">
          <RotateCcw size={18} color={theme.palette.secondary.main} />
          <Typography variant="h6" fontWeight={600} sx={{ fontSize: '1rem' }}>
            {t('lastRestoreSection.title')}
          </Typography>
        </Stack>
        <Button
          variant="outlined"
          size="small"
          startIcon={<ExternalLink size={14} />}
          onClick={() => navigate('/activity')}
          sx={{
            textTransform: 'none',
            fontSize: '0.78rem',
            height: 30,
            borderRadius: 1.5,
            borderColor: isDark ? alpha('#fff', 0.15) : alpha('#000', 0.15),
            color: 'text.secondary',
            '&:hover': {
              borderColor: isDark ? alpha('#fff', 0.3) : alpha('#000', 0.25),
              bgcolor: isDark ? alpha('#fff', 0.05) : alpha('#000', 0.04),
            },
          }}
        >
          {t('lastRestoreSection.viewAll')}
        </Button>
      </Stack>

      <Box sx={cardSx}>
        <RestoreJobCard job={restoreJob} showJobId={false} />
      </Box>
    </Box>
  )
}
