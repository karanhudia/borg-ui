import React from 'react'
import { Card, CardContent, Typography, Stack, Box } from '@mui/material'
import { Calendar } from 'lucide-react'
import { formatDate, formatRelativeTime } from '../utils/dateUtils'

interface Repository {
  id: number
  name: string
  path: string
}

interface UpcomingJob {
  id: number
  name: string
  repository?: string
  repository_id?: number
  repository_ids?: number[]
  next_run: string
  cron_expression: string
}

interface UpcomingJobsTableProps {
  upcomingJobs: UpcomingJob[]
  repositories: Repository[]
  isLoading: boolean
  onRunNow?: (jobId: number) => void
  getRepositoryName: (path: string) => string
}

const UpcomingJobsTable: React.FC<UpcomingJobsTableProps> = ({
  upcomingJobs,
  repositories,
  getRepositoryName,
}) => {
  if (upcomingJobs.length === 0) {
    return null
  }

  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
          <Calendar size={20} color="#1976d2" />
          <Typography variant="h6" fontWeight={600}>
            Upcoming Jobs (Next 24 Hours)
          </Typography>
        </Stack>
        <Stack spacing={1.5}>
          {upcomingJobs.slice(0, 5).map((job) => (
            <Box
              key={job.id}
              sx={{
                p: 2,
                backgroundColor: 'action.hover',
                borderRadius: 1,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <Box>
                <Typography variant="body2" fontWeight={500}>
                  {job.name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {job.repository_ids && job.repository_ids.length > 0
                    ? `${job.repository_ids.length} repositories`
                    : job.repository_id
                      ? repositories.find((r) => r.id === job.repository_id)?.name || 'Unknown'
                      : getRepositoryName(job.repository || '')}
                </Typography>
              </Box>
              <Box sx={{ textAlign: 'right' }}>
                <Typography variant="body2" fontWeight={500}>
                  {formatDate(job.next_run)}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {formatRelativeTime(job.next_run)}
                </Typography>
              </Box>
            </Box>
          ))}
        </Stack>
      </CardContent>
    </Card>
  )
}

export default UpcomingJobsTable
