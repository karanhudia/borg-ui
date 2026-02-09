import { Card, CardContent, Stack, Typography, Box } from '@mui/material'
import { RotateCcw } from 'lucide-react'
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
  if (!restoreJob) {
    return (
      <Card sx={{ mb: 4, border: 1, borderColor: 'divider', bgcolor: 'background.paper' }}>
        <CardContent>
          <Stack direction="row" spacing={2} alignItems="center">
            <RotateCcw size={24} color="#757575" />
            <Box>
              <Typography variant="body2" color="text.secondary">
                No restores performed yet from this repository
              </Typography>
            </Box>
          </Stack>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card sx={{ mb: 4, border: 1, borderColor: 'divider' }}>
      <CardContent>
        <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
          <RotateCcw size={24} color="#9c27b0" />
          <Typography variant="h6" fontWeight={600}>
            Last Restore
          </Typography>
        </Stack>

        <RestoreJobCard job={restoreJob} showJobId={false} />
      </CardContent>
    </Card>
  )
}
