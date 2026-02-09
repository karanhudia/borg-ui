import { Card, CardContent, Stack, Typography, Box, Button } from '@mui/material'
import { RotateCcw, ExternalLink } from 'lucide-react'
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
  const navigate = useNavigate()

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
    <Box sx={{ mb: 4 }}>
      <Stack direction="row" spacing={1.5} alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <RotateCcw size={20} color="#9c27b0" />
          <Typography variant="h6" fontWeight={600}>
            Last Restore
          </Typography>
        </Stack>
        <Button
          variant="outlined"
          size="small"
          startIcon={<ExternalLink size={16} />}
          onClick={() => navigate('/activity')}
          sx={{ textTransform: 'none' }}
        >
          View All Restores
        </Button>
      </Stack>

      <Card sx={{ border: 1, borderColor: 'divider' }}>
        <CardContent>
          <RestoreJobCard job={restoreJob} showJobId={false} />
        </CardContent>
      </Card>
    </Box>
  )
}
