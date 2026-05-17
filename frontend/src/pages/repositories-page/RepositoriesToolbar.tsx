import { Search } from '@mui/icons-material'
import { Box, InputBase, MenuItem, Select, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
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

  return (
    <Box sx={{ mb: 3, display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
      <Box
        sx={{
          flex: '1 1 100%',
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          px: 1.5,
          height: 40,
          borderRadius: 1.5,
          border: '1px solid',
          borderColor: isDark ? alpha('#fff', 0.1) : alpha('#000', 0.12),
          bgcolor: isDark ? alpha('#fff', 0.04) : alpha('#000', 0.02),
          '&:focus-within': {
            borderColor: isDark ? alpha('#fff', 0.2) : alpha('#000', 0.25),
          },
        }}
      >
        <Search sx={{ fontSize: 16, color: 'text.disabled', flexShrink: 0 }} />
        <InputBase
          placeholder={t('repositories.search')}
          value={searchQuery}
          onChange={(event) => onSearchChange(event.target.value)}
          sx={{ flex: 1, fontSize: '0.875rem', minWidth: 0 }}
        />
      </Box>

      <Select
        size="small"
        value={sortBy}
        onChange={(event) => {
          const nextSort = event.target.value
          onSortChange(nextSort)
          onFilterTracked({
            filter_kind: 'sort',
            sort_by: nextSort,
            group_by: groupBy,
            query_length: searchQuery.trim().length,
            result_count: getRepositoryResultCount(processedRepositories),
          })
        }}
        sx={selectSx(isDark)}
      >
        <MenuItem value="name-asc">{t('repositories.sort.nameAZ')}</MenuItem>
        <MenuItem value="name-desc">{t('repositories.sort.nameZA')}</MenuItem>
        <MenuItem value="last-backup-recent">{t('repositories.sort.lastBackupRecent')}</MenuItem>
        <MenuItem value="last-backup-oldest">{t('repositories.sort.lastBackupOldest')}</MenuItem>
        <MenuItem value="created-newest">{t('repositories.sort.createdNewest')}</MenuItem>
        <MenuItem value="created-oldest">{t('repositories.sort.createdOldest')}</MenuItem>
      </Select>

      <Select
        size="small"
        value={groupBy}
        onChange={(event) => {
          const nextGroup = event.target.value
          onGroupChange(nextGroup)
          onFilterTracked({
            filter_kind: 'group',
            sort_by: sortBy,
            group_by: nextGroup,
            query_length: searchQuery.trim().length,
            result_count: getRepositoryResultCount(processedRepositories),
          })
        }}
        sx={selectSx(isDark, 120)}
      >
        <MenuItem value="none">{t('repositories.group.none')}</MenuItem>
        <MenuItem value="location">{t('repositories.group.hostname')}</MenuItem>
        <MenuItem value="type">{t('repositories.group.type')}</MenuItem>
        <MenuItem value="mode">{t('repositories.group.mode')}</MenuItem>
      </Select>

      {showBackupPlanFilter && (
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
          sx={selectSx(isDark, 180)}
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
      )}
    </Box>
  )
}

function selectSx(isDark: boolean, minWidth = 160) {
  return {
    flex: 1,
    minWidth,
    fontSize: '0.8rem',
    fontWeight: 600,
    borderRadius: 1.5,
    '& .MuiOutlinedInput-notchedOutline': {
      borderColor: isDark ? alpha('#fff', 0.1) : alpha('#000', 0.12),
    },
    '&:hover .MuiOutlinedInput-notchedOutline': {
      borderColor: isDark ? alpha('#fff', 0.2) : alpha('#000', 0.25),
    },
  }
}
