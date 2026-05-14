import { Add, FileUpload, FilterList, Storage } from '@mui/icons-material'
import { Box, Button, Divider, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import EmptyStateCard from '../../components/EmptyStateCard'
import RepositoryCard from '../../components/RepositoryCard'
import RepositoryCardSkeleton from '../../components/RepositoryCardSkeleton'
import type { RepoAction } from '../../hooks/usePermissions'
import type { ProcessedRepositories, Repository } from './types'

interface RepositoryGroupsProps {
  isLoading: boolean
  repositories: Repository[]
  processedRepositories: ProcessedRepositories
  repositoriesWithJobs: Set<number>
  searchQuery: string
  canManageRepositoriesGlobally: boolean
  canDo: (repositoryId: number, action: RepoAction) => boolean
  onSearchChange: (value: string) => void
  onOpenWizard: (mode: 'create' | 'edit' | 'import', repository?: Repository) => void
  onViewInfo: (repository: Repository) => void
  onCheck: (repository: Repository) => void
  onCompact: (repository: Repository) => void
  onPrune: (repository: Repository) => void
  onEdit: (repository: Repository) => void
  onDelete: (repository: Repository) => void
  onBackupNow: (repository: Repository) => void
  onViewArchives: (repository: Repository) => void
  onCreateBackupPlan: (repository: Repository) => void
  getCompressionLabel: (compression: string) => string
  onJobCompleted: (repositoryId: number) => void
}

export function RepositoryGroups({
  isLoading,
  repositories,
  processedRepositories,
  repositoriesWithJobs,
  searchQuery,
  canManageRepositoriesGlobally,
  canDo,
  onSearchChange,
  onOpenWizard,
  onViewInfo,
  onCheck,
  onCompact,
  onPrune,
  onEdit,
  onDelete,
  onBackupNow,
  onViewArchives,
  onCreateBackupPlan,
  getCompressionLabel,
  onJobCompleted,
}: RepositoryGroupsProps) {
  const { t } = useTranslation()

  if (isLoading) {
    return (
      <Stack spacing={2}>
        {[0, 1, 2].map((index) => (
          <RepositoryCardSkeleton key={index} index={index} />
        ))}
      </Stack>
    )
  }

  if (repositories.length === 0) {
    return (
      <EmptyStateCard
        icon={<Storage sx={{ fontSize: 64 }} />}
        title={t('repositories.empty.title')}
        description={t('repositories.empty.subtitle')}
        secondaryDescription={t('repositories.empty.hint')}
        actions={
          canManageRepositoriesGlobally && (
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} justifyContent="center">
              <Button
                variant="contained"
                startIcon={<Add />}
                onClick={() => onOpenWizard('create')}
                sx={{ width: { xs: '100%', sm: 'auto' } }}
              >
                {t('repositories.createRepository')}
              </Button>
              <Button
                variant="outlined"
                startIcon={<FileUpload />}
                onClick={() => onOpenWizard('import')}
                sx={{ width: { xs: '100%', sm: 'auto' } }}
              >
                {t('repositories.importExisting')}
              </Button>
            </Stack>
          )
        }
      />
    )
  }

  if (
    processedRepositories.groups.length === 0 ||
    processedRepositories.groups.every((group) => group.repositories.length === 0)
  ) {
    return (
      <EmptyStateCard
        icon={<Storage sx={{ fontSize: 64 }} />}
        title={t('repositories.noMatch.title')}
        description={
          searchQuery
            ? t('repositories.noMatch.message', { search: searchQuery })
            : t('repositories.noMatch.fallback')
        }
        actions={
          searchQuery && (
            <Button variant="outlined" onClick={() => onSearchChange('')}>
              {t('repositories.noMatch.clearSearch')}
            </Button>
          )
        }
      />
    )
  }

  return (
    <Stack spacing={3}>
      {processedRepositories.groups.map((group, groupIndex) => (
        <Box key={groupIndex}>
          {group.name && (
            <Box sx={{ mb: 2 }}>
              <Typography
                variant="h6"
                sx={{
                  fontSize: '1rem',
                  fontWeight: 600,
                  color: 'primary.main',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                }}
              >
                <FilterList fontSize="small" />
                {group.name}
                <Typography
                  component="span"
                  sx={{ ml: 0.5, fontSize: '0.875rem', color: 'text.secondary' }}
                >
                  ({group.repositories.length})
                </Typography>
              </Typography>
              <Divider sx={{ mt: 1 }} />
            </Box>
          )}

          <Stack spacing={2} sx={{ minWidth: 0 }}>
            {group.repositories.map((repository) => (
              <RepositoryCard
                key={repository.id}
                repository={repository}
                isInJobsSet={repositoriesWithJobs.has(repository.id)}
                onViewInfo={() => onViewInfo(repository)}
                onCheck={() => onCheck(repository)}
                onCompact={() => onCompact(repository)}
                onPrune={() => onPrune(repository)}
                onEdit={() => onEdit(repository)}
                onDelete={() => onDelete(repository)}
                onBackupNow={() => onBackupNow(repository)}
                onViewArchives={() => onViewArchives(repository)}
                onCreateBackupPlan={() => onCreateBackupPlan(repository)}
                getCompressionLabel={getCompressionLabel}
                canManageRepository={canManageRepositoriesGlobally}
                canDo={(action) => canDo(repository.id, action)}
                onJobCompleted={onJobCompleted}
              />
            ))}
          </Stack>
        </Box>
      ))}
    </Stack>
  )
}
