import React, { useState } from 'react'
import { Box, Collapse, IconButton, Typography, alpha, useTheme } from '@mui/material'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Repository } from '../types'
import RepoScheduleRow from './RepoScheduleRow'
import type { RepoScheduleData } from './PlanScheduleCard'

interface UnassignedReposSectionProps {
  repositories: Repository[]
  repoSchedules: Record<number, RepoScheduleData>
  onEditRepoCheck: (repoId: number) => void
  onEditRepoRestore: (repoId: number) => void
  canManageRepo: (repoId: number) => boolean
}

const UnassignedReposSection: React.FC<UnassignedReposSectionProps> = ({
  repositories,
  repoSchedules,
  onEditRepoCheck,
  onEditRepoRestore,
  canManageRepo,
}) => {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const [expanded, setExpanded] = useState(false)

  if (repositories.length === 0) return null

  return (
    <Box
      sx={{
        borderRadius: 2,
        bgcolor: 'background.paper',
        border: '1px solid',
        borderColor: isDark ? alpha('#fff', 0.08) : alpha('#000', 0.08),
        overflow: 'hidden',
      }}
    >
      <Box
        sx={{
          px: { xs: 1.75, sm: 2 },
          py: 1.25,
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          cursor: 'pointer',
          '&:hover': {
            bgcolor: isDark ? alpha('#fff', 0.03) : alpha('#000', 0.02),
          },
        }}
        onClick={() => setExpanded((v) => !v)}
      >
        <IconButton size="small" sx={{ ml: -0.5 }} aria-label={expanded ? 'Collapse' : 'Expand'}>
          {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </IconButton>
        <Typography variant="subtitle2" fontWeight={700} sx={{ flex: 1 }}>
          {t('schedule.byPlan.unassignedTitle', {
            defaultValue: 'Repositories not in any plan ({{count}})',
            count: repositories.length,
          })}
        </Typography>
      </Box>
      <Collapse in={expanded} unmountOnExit>
        <Box
          sx={{
            borderTop: '1px solid',
            borderColor: 'divider',
            bgcolor: isDark ? alpha('#fff', 0.02) : alpha('#000', 0.02),
            px: { xs: 1, sm: 1.5 },
          }}
        >
          {repositories.map((repo) => {
            const sched = repoSchedules[repo.id]
            return (
              <RepoScheduleRow
                key={repo.id}
                repositoryId={repo.id}
                repositoryName={repo.name}
                repositoryPath={repo.path}
                checkCron={sched?.checkCron ?? null}
                checkTimezone={sched?.checkTimezone}
                checkEnabled={sched?.checkEnabled ?? true}
                restoreCron={sched?.restoreCron ?? null}
                restoreTimezone={sched?.restoreTimezone}
                restoreEnabled={sched?.restoreEnabled ?? true}
                onEditCheck={onEditRepoCheck}
                onEditRestore={onEditRepoRestore}
                canManage={canManageRepo(repo.id)}
              />
            )
          })}
        </Box>
      </Collapse>
    </Box>
  )
}

export default UnassignedReposSection
