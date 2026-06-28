import { useTranslation } from 'react-i18next'
import { Box, MenuItem, Select } from '@mui/material'

interface ActivityFiltersProps {
  typeFilter: string
  statusFilter: string
  onTypeFilterChange: (value: string) => void
  onStatusFilterChange: (value: string) => void
}

export function ActivityFilters({
  typeFilter,
  statusFilter,
  onTypeFilterChange,
  onStatusFilterChange,
}: ActivityFiltersProps) {
  const { t } = useTranslation()

  return (
    <Box sx={{ mb: 3, display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
      <Select
        size="small"
        value={typeFilter}
        onChange={(event) => onTypeFilterChange(event.target.value)}
        sx={{ minWidth: 160, fontSize: '0.8rem', fontWeight: 600, borderRadius: 1.5 }}
      >
        <MenuItem value="all">{t('activity.filters.allTypes')}</MenuItem>
        <MenuItem value="backup">{t('activity.filters.types.backup')}</MenuItem>
        <MenuItem value="restore">{t('activity.filters.types.restore')}</MenuItem>
        <MenuItem value="restore_check">{t('activity.filters.types.restoreCheck')}</MenuItem>
        <MenuItem value="check">{t('activity.filters.types.check')}</MenuItem>
        <MenuItem value="compact">{t('activity.filters.types.compact')}</MenuItem>
        <MenuItem value="prune">{t('activity.filters.types.prune')}</MenuItem>
        <MenuItem value="package">{t('activity.filters.types.package')}</MenuItem>
        <MenuItem value="rclone_sync">{t('activity.filters.types.rcloneSync')}</MenuItem>
        <MenuItem value="rclone_hydrate">{t('activity.filters.types.rcloneHydrate')}</MenuItem>
        <MenuItem value="script_execution">{t('activity.filters.types.scriptExecution')}</MenuItem>
      </Select>

      <Select
        size="small"
        value={statusFilter}
        onChange={(event) => onStatusFilterChange(event.target.value)}
        sx={{ minWidth: 210, fontSize: '0.8rem', fontWeight: 600, borderRadius: 1.5 }}
      >
        <MenuItem value="all">{t('activity.filters.allStatus')}</MenuItem>
        <MenuItem value="completed">{t('activity.filters.statuses.completed')}</MenuItem>
        <MenuItem value="completed_with_warnings">
          {t('activity.filters.statuses.completedWithWarnings')}
        </MenuItem>
        <MenuItem value="needs_backup">{t('activity.filters.statuses.needsBackup')}</MenuItem>
        <MenuItem value="failed">{t('activity.filters.statuses.failed')}</MenuItem>
        <MenuItem value="running">{t('activity.filters.statuses.running')}</MenuItem>
        <MenuItem value="pending">{t('activity.filters.statuses.pending')}</MenuItem>
      </Select>
    </Box>
  )
}
