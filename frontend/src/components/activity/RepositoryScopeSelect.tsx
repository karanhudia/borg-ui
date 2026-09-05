import { MenuItem, Box, Typography } from '@mui/material'
import { Layers } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import RepoSelect from '../RepoSelect'
import { repositoriesAPI } from '../../services/api'
import type { Repository } from '@/types'

interface RepositoryScopeSelectProps {
  value: number | null
}

const ALL = 'all'

// The way into (and between) repository-scoped activity views, built on
// the shared repository select so it looks like every other repository
// picker. "All repositories" is the global ledger; any repository opens
// its own Operations view at /activity?repository_id=.
export default function RepositoryScopeSelect({ value }: RepositoryScopeSelectProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })
  const repositories: Repository[] = data?.data?.repositories ?? []
  const allLabel = t('activity.repositoryScope.all')

  return (
    <RepoSelect
      repositories={repositories}
      loading={isLoading}
      valueKey="id"
      value={value ?? ALL}
      label={t('activity.repositoryScope.label')}
      fallbackDisplayValue={allLabel}
      fullWidth
      prefixItems={
        <MenuItem value={ALL}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Layers size={16} />
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {allLabel}
            </Typography>
          </Box>
        </MenuItem>
      }
      onChange={(next) => navigate(next === ALL ? '/activity' : `/activity?repository_id=${next}`)}
    />
  )
}
