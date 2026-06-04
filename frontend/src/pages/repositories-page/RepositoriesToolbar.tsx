import { MenuItem, Select, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import ListToolbar from '../../components/ListToolbar'
import { listToolbarSelectSx } from '../../components/listToolbarStyles'
import type { ProcessedRepositories } from './types'
import { getRepositoryResultCount } from './helpers'

interface BackupPlanFilterOption {
  id: number
  name: string
}

interface RepositoriesToolbarProps {
  isVisible: boolean
  searchQuery: string
  sortBy: string
  groupBy: string
  processedRepositories: ProcessedRepositories
  backupPlans: BackupPlanFilterOption[]
  backupPlanFilterLoading: boolean
  selectedBackupPlanId: number | null
  onSearchChange: (value: string) => void
  onSortChange: (value: string) => void
  onGroupChange: (value: string) => void
  onBackupPlanFilterChange: (planId: number | null) => void
  onFilterTracked: (metadata: {
    filter_kind: 'sort' | 'group' | 'backup_plan'
    sort_by: string
    group_by: string
    backup_plan_id?: number | null
    query_length: number
    result_count: number
  }) => void
}

export function RepositoriesToolbar({
  isVisible,
  searchQuery,
  sortBy,
  groupBy,
  processedRepositories,
  backupPlans,
  backupPlanFilterLoading,
  selectedBackupPlanId,
  onSearchChange,
  onSortChange,
  onGroupChange,
  onBackupPlanFilterChange,
  onFilterTracked,
}: RepositoriesToolbarProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const selectedPlanVisible =
    selectedBackupPlanId === null || backupPlans.some((plan) => plan.id === selectedBackupPlanId)
  const showBackupPlanFilter =
    backupPlanFilterLoading || backupPlans.length > 0 || selectedBackupPlanId !== null

  if (!isVisible) {
    return null
  }

  const trackedSortChange = (nextSort: string) => {
    onSortChange(nextSort)
    onFilterTracked({
      filter_kind: 'sort',
      sort_by: nextSort,
      group_by: groupBy,
      query_length: searchQuery.trim().length,
      result_count: getRepositoryResultCount(processedRepositories),
    })
  }

  const trackedGroupChange = (nextGroup: string) => {
    onGroupChange(nextGroup)
    onFilterTracked({
      filter_kind: 'group',
      sort_by: sortBy,
      group_by: nextGroup,
      query_length: searchQuery.trim().length,
      result_count: getRepositoryResultCount(processedRepositories),
    })
  }

  return (
    <ListToolbar
      searchValue={searchQuery}
      onSearchChange={onSearchChange}
      searchPlaceholder={t('repositories.search')}
      sortValue={sortBy}
      onSortChange={trackedSortChange}
      sortMinWidth={160}
      sortOptions={[
        { value: 'name-asc', label: t('repositories.sort.nameAZ') },
        { value: 'name-desc', label: t('repositories.sort.nameZA') },
        { value: 'last-backup-recent', label: t('repositories.sort.lastBackupRecent') },
        { value: 'last-backup-oldest', label: t('repositories.sort.lastBackupOldest') },
        { value: 'created-newest', label: t('repositories.sort.createdNewest') },
        { value: 'created-oldest', label: t('repositories.sort.createdOldest') },
      ]}
      groupValue={groupBy}
      onGroupChange={trackedGroupChange}
      groupMinWidth={120}
      groupOptions={[
        { value: 'none', label: t('repositories.group.none') },
        { value: 'location', label: t('repositories.group.hostname') },
        { value: 'type', label: t('repositories.group.type') },
        { value: 'mode', label: t('repositories.group.mode') },
      ]}
      extraFilters={
        showBackupPlanFilter ? (
          <Select
            size="small"
            value={selectedBackupPlanId === null ? '' : String(selectedBackupPlanId)}
            displayEmpty
            disabled={backupPlanFilterLoading && backupPlans.length === 0}
            inputProps={{ 'aria-label': t('repositories.filter.backupPlan') }}
            onChange={(event) => {
              const value = event.target.value
              const nextPlanId = value ? Number(value) : null
              onBackupPlanFilterChange(nextPlanId)
              onFilterTracked({
                filter_kind: 'backup_plan',
                sort_by: sortBy,
                group_by: groupBy,
                backup_plan_id: nextPlanId,
                query_length: searchQuery.trim().length,
                result_count: getRepositoryResultCount(processedRepositories),
              })
            }}
            sx={listToolbarSelectSx(isDark, 180)}
          >
            <MenuItem value="">{t('repositories.filter.allBackupPlans')}</MenuItem>
            {!selectedPlanVisible && selectedBackupPlanId !== null && (
              <MenuItem value={String(selectedBackupPlanId)}>
                {t('repositories.filter.backupPlanFallback', { id: selectedBackupPlanId })}
              </MenuItem>
            )}
            {backupPlans.map((plan) => (
              <MenuItem key={plan.id} value={String(plan.id)}>
                {plan.name}
              </MenuItem>
            ))}
          </Select>
        ) : null
      }
    />
  )
}
