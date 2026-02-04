import React from 'react'
import { Stack, Card, CardContent, Typography, Box, Chip, Alert, Divider } from '@mui/material'
import { CheckCircle, Calendar, Code, Wrench } from 'lucide-react'
import { Repository, Script } from '../../ScheduleWizard'

interface WizardStepScheduleReviewProps {
  data: {
    name: string
    description: string
    repositoryIds: number[]
    cronExpression: string
    archiveNameTemplate: string
    preBackupScriptId: number | null
    postBackupScriptId: number | null
    runRepositoryScripts: boolean
    runPruneAfter: boolean
    runCompactAfter: boolean
    pruneKeepHourly: number
    pruneKeepDaily: number
    pruneKeepWeekly: number
    pruneKeepMonthly: number
    pruneKeepQuarterly: number
    pruneKeepYearly: number
  }
  repositories: Repository[]
  scripts: Script[]
}

const WizardStepScheduleReview: React.FC<WizardStepScheduleReviewProps> = ({
  data,
  repositories,
  scripts,
}) => {
  const selectedRepos = repositories.filter((r) => data.repositoryIds.includes(r.id))
  const preScript = scripts.find((s) => s.id === data.preBackupScriptId)
  const postScript = scripts.find((s) => s.id === data.postBackupScriptId)

  return (
    <Stack spacing={2}>
      <Alert severity="success" icon={<CheckCircle size={20} />} sx={{ py: 0.5 }}>
        <Typography variant="body2" fontWeight={600}>
          Ready to create schedule!
        </Typography>
        <Typography variant="caption">Review and confirm below.</Typography>
      </Alert>

      {/* Job Summary Card */}
      <Card variant="outlined">
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
            <Calendar size={20} color="#1976d2" />
            <Typography variant="h6" fontWeight={600}>
              Job Summary
            </Typography>
          </Box>

          <Stack spacing={1.5}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Name
              </Typography>
              <Typography variant="body1" fontWeight={600}>
                {data.name}
              </Typography>
              {data.description && (
                <Typography variant="body2" color="text.secondary">
                  {data.description}
                </Typography>
              )}
            </Box>

            <Divider />

            <Box>
              <Typography variant="caption" color="text.secondary">
                Repositories ({selectedRepos.length})
              </Typography>
              <Stack spacing={0.5} sx={{ mt: 0.5 }}>
                {selectedRepos.map((repo, index) => (
                  <Box key={repo.id} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Chip
                      label={`${index + 1}`}
                      size="small"
                      sx={{ width: 24, height: 20, fontSize: '0.7rem' }}
                    />
                    <Typography variant="body2">{repo.name}</Typography>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ fontFamily: 'monospace' }}
                    >
                      {repo.path}
                    </Typography>
                  </Box>
                ))}
              </Stack>
            </Box>

            <Divider />

            <Box>
              <Typography variant="caption" color="text.secondary">
                Schedule
              </Typography>
              <Typography variant="body1" fontWeight={600} sx={{ fontFamily: 'monospace' }}>
                {data.cronExpression}
              </Typography>
            </Box>

            <Box>
              <Typography variant="caption" color="text.secondary">
                Archive Name Template
              </Typography>
              <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                {data.archiveNameTemplate}
              </Typography>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      {/* Scripts Configuration Card */}
      <Card variant="outlined">
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
            <Code size={20} color="#7b1fa2" />
            <Typography variant="h6" fontWeight={600}>
              Scripts Configuration
            </Typography>
          </Box>

          <Stack spacing={1.5}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Pre-Backup Script
              </Typography>
              <Typography variant="body2">{preScript ? preScript.name : <em>None</em>}</Typography>
            </Box>

            <Box>
              <Typography variant="caption" color="text.secondary">
                Post-Backup Script
              </Typography>
              <Typography variant="body2">
                {postScript ? postScript.name : <em>None</em>}
              </Typography>
            </Box>

            <Box>
              <Typography variant="caption" color="text.secondary">
                Repository-Level Scripts
              </Typography>
              <Chip
                label={data.runRepositoryScripts ? 'Enabled' : 'Disabled'}
                color={data.runRepositoryScripts ? 'primary' : 'default'}
                size="small"
              />
            </Box>
          </Stack>
        </CardContent>
      </Card>

      {/* Maintenance Settings Card */}
      <Card variant="outlined">
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
            <Wrench size={20} color="#2e7d32" />
            <Typography variant="h6" fontWeight={600}>
              Maintenance Settings
            </Typography>
          </Box>

          <Stack spacing={1.5}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Prune After Backup
              </Typography>
              <Box sx={{ mt: 0.5 }}>
                <Chip
                  label={data.runPruneAfter ? 'Enabled' : 'Disabled'}
                  color={data.runPruneAfter ? 'primary' : 'default'}
                  size="small"
                />
              </Box>
              {data.runPruneAfter && (
                <Typography
                  variant="body2"
                  sx={{ mt: 1, fontFamily: 'monospace', fontSize: '0.875rem' }}
                >
                  Keep: {data.pruneKeepHourly > 0 ? `${data.pruneKeepHourly}h / ` : ''}
                  {data.pruneKeepDaily}d / {data.pruneKeepWeekly}w / {data.pruneKeepMonthly}m /{' '}
                  {data.pruneKeepQuarterly > 0 ? `${data.pruneKeepQuarterly}q / ` : ''}
                  {data.pruneKeepYearly}y
                </Typography>
              )}
            </Box>

            <Box>
              <Typography variant="caption" color="text.secondary">
                Compact After Prune
              </Typography>
              <Box sx={{ mt: 0.5 }}>
                <Chip
                  label={data.runCompactAfter ? 'Enabled' : 'Disabled'}
                  color={data.runCompactAfter ? 'secondary' : 'default'}
                  size="small"
                />
              </Box>
            </Box>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  )
}

export default WizardStepScheduleReview
