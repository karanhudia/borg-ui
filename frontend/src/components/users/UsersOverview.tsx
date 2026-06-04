import React from 'react'
import { useTranslation } from 'react-i18next'
import {
  Alert,
  Box,
  Button,
  Chip,
  InputAdornment,
  TextField,
  Tooltip,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { Plus, Search } from 'lucide-react'
import { RoleFilter, StatusFilter } from './types'

interface UsersHeaderProps {
  canCreateUser: boolean
  onCreateUser: () => void
}

export const UsersHeader: React.FC<UsersHeaderProps> = ({ canCreateUser, onCreateUser }) => {
  const { t } = useTranslation()

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: { xs: 'column', sm: 'row' },
        justifyContent: 'space-between',
        alignItems: { xs: 'stretch', sm: 'center' },
        gap: 1.5,
      }}
    >
      <Box>
        <Typography variant="h6" fontWeight={600}>
          {t('settings.users.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('settings.users.subtitle')}
        </Typography>
      </Box>
      <Tooltip title={!canCreateUser ? t('settings.users.planCaption') : ''} arrow>
        <span>
          <Button
            variant="contained"
            startIcon={<Plus size={18} />}
            onClick={onCreateUser}
            disabled={!canCreateUser}
            sx={{ width: { xs: '100%', sm: 'auto' } }}
          >
            {t('settings.users.addUser')}
          </Button>
        </span>
      </Tooltip>
    </Box>
  )
}

interface UsersStatsProps {
  totalUsers: number
  activeUsers: number
  pendingSsoUsers: number
  adminUsers: number
  operatorUsers: number
  viewerUsers: number
}

export const UsersStats: React.FC<UsersStatsProps> = ({
  totalUsers,
  activeUsers,
  pendingSsoUsers,
  adminUsers,
  operatorUsers,
  viewerUsers,
}) => {
  const { t } = useTranslation()
  const stats = [
    { label: t('settings.users.stats.total'), value: totalUsers, color: 'text.primary' },
    { label: t('settings.users.stats.active'), value: activeUsers, color: 'success.main' },
    {
      label: t('settings.users.stats.pendingSso'),
      value: pendingSsoUsers,
      color: 'warning.main',
    },
    { label: t('settings.users.stats.admins'), value: adminUsers, color: 'secondary.main' },
    {
      label: t('settings.users.stats.operators'),
      value: operatorUsers,
      color: 'info.main',
    },
    {
      label: t('settings.users.stats.viewers'),
      value: viewerUsers,
      color: 'text.secondary',
    },
  ]

  return (
    <Box sx={{ display: 'flex', gap: { xs: 3, sm: 4 }, flexWrap: 'wrap' }}>
      {stats.map((stat) => (
        <Box key={stat.label}>
          <Typography
            variant="h6"
            fontWeight={700}
            sx={{ color: stat.color, lineHeight: 1, mb: 0.25 }}
          >
            {stat.value}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {stat.label}
          </Typography>
        </Box>
      ))}
    </Box>
  )
}

interface PendingSsoAlertProps {
  pendingSsoUsers: number
  statusFilter: StatusFilter
  onSetStatusFilter: (statusFilter: StatusFilter) => void
}

export const PendingSsoAlert: React.FC<PendingSsoAlertProps> = ({
  pendingSsoUsers,
  statusFilter,
  onSetStatusFilter,
}) => {
  const { t } = useTranslation()

  if (pendingSsoUsers <= 0) return null

  return (
    <Alert
      severity="warning"
      action={
        <Button
          color="inherit"
          size="small"
          onClick={() => onSetStatusFilter('pending_sso')}
          disabled={statusFilter === 'pending_sso'}
        >
          {t('settings.users.pendingReview.action')}
        </Button>
      }
    >
      <Typography variant="body2" fontWeight={600}>
        {t('settings.users.pendingReview.title', { count: pendingSsoUsers })}
      </Typography>
      <Typography variant="body2">{t('settings.users.pendingReview.description')}</Typography>
    </Alert>
  )
}

interface UsersFilterToolbarProps {
  loadingUsers: boolean
  userCount: number
  filteredUserCount: number
  totalUsers: number
  searchQuery: string
  roleFilter: RoleFilter
  statusFilter: StatusFilter
  hasActiveFilters: boolean
  onSearchQueryChange: (value: string) => void
  onRoleFilterChange: (roleFilter: RoleFilter) => void
  onStatusFilterChange: (statusFilter: StatusFilter) => void
}

export const UsersFilterToolbar: React.FC<UsersFilterToolbarProps> = ({
  loadingUsers,
  userCount,
  filteredUserCount,
  totalUsers,
  searchQuery,
  roleFilter,
  statusFilter,
  hasActiveFilters,
  onSearchQueryChange,
  onRoleFilterChange,
  onStatusFilterChange,
}) => {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const roleFilterOptions: { value: RoleFilter; label: string; color?: string }[] = [
    { value: 'all', label: t('settings.users.filter.allRoles') },
    { value: 'admin', label: t('settings.users.roles.admin'), color: '#7c3aed' },
    { value: 'operator', label: t('settings.users.roles.operator'), color: '#0891b2' },
    { value: 'viewer', label: t('settings.users.roles.viewer'), color: '#059669' },
  ]

  const statusFilterOptions: { value: StatusFilter; label: string }[] = [
    { value: 'all', label: t('settings.users.filter.allStatuses') },
    { value: 'active', label: t('settings.users.status.active') },
    { value: 'inactive', label: t('settings.users.status.inactive') },
    { value: 'pending_sso', label: t('settings.users.status.pendingSso') },
  ]

  if (loadingUsers || userCount === 0) return null

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      <Box
        sx={{
          display: 'flex',
          gap: 1.5,
          alignItems: 'center',
          flexWrap: 'nowrap',
          overflow: 'hidden',
        }}
      >
        <TextField
          size="small"
          placeholder={t('settings.users.search.placeholder')}
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search size={15} color={theme.palette.text.secondary} />
              </InputAdornment>
            ),
          }}
          sx={{
            width: 240,
            flexShrink: 0,
            '& .MuiOutlinedInput-root': { borderRadius: 1.5 },
          }}
        />

        <Box sx={{ display: 'flex', gap: 0.75, flexShrink: 0 }}>
          {roleFilterOptions.map((opt) => {
            const isSelected = roleFilter === opt.value
            const chipColor = opt.color
            return (
              <Chip
                key={opt.value}
                label={opt.label}
                size="small"
                onClick={() => onRoleFilterChange(opt.value)}
                sx={{
                  cursor: 'pointer',
                  fontWeight: isSelected ? 600 : 400,
                  transition: 'all 150ms ease',
                  ...(isSelected && chipColor
                    ? {
                        bgcolor: alpha(chipColor, isDark ? 0.25 : 0.12),
                        color: chipColor,
                        border: '1px solid',
                        borderColor: alpha(chipColor, 0.4),
                        '&:hover': { bgcolor: alpha(chipColor, isDark ? 0.32 : 0.18) },
                      }
                    : isSelected
                      ? {
                          bgcolor: isDark ? alpha('#fff', 0.12) : alpha('#000', 0.08),
                          '&:hover': {
                            bgcolor: isDark ? alpha('#fff', 0.16) : alpha('#000', 0.12),
                          },
                        }
                      : {
                          bgcolor: 'transparent',
                          border: '1px solid',
                          borderColor: isDark ? alpha('#fff', 0.12) : alpha('#000', 0.1),
                          color: 'text.secondary',
                          '&:hover': {
                            bgcolor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.04),
                            borderColor: isDark ? alpha('#fff', 0.2) : alpha('#000', 0.18),
                          },
                        }),
                }}
              />
            )
          })}
        </Box>

        <Box sx={{ display: 'flex', gap: 0.75, flexShrink: 0 }}>
          {statusFilterOptions.map((opt) => {
            const isSelected = statusFilter === opt.value
            const dotColor =
              opt.value === 'active'
                ? theme.palette.success.main
                : opt.value === 'inactive'
                  ? theme.palette.error.main
                  : opt.value === 'pending_sso'
                    ? theme.palette.warning.main
                    : undefined
            return (
              <Chip
                key={opt.value}
                size="small"
                onClick={() => onStatusFilterChange(opt.value)}
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6 }}>
                    {dotColor && (
                      <Box
                        sx={{
                          width: 6,
                          height: 6,
                          borderRadius: '50%',
                          bgcolor: dotColor,
                          flexShrink: 0,
                        }}
                      />
                    )}
                    {opt.label}
                  </Box>
                }
                sx={{
                  cursor: 'pointer',
                  fontWeight: isSelected ? 600 : 400,
                  transition: 'all 150ms ease',
                  ...(isSelected
                    ? {
                        bgcolor: isDark ? alpha('#fff', 0.12) : alpha('#000', 0.08),
                        '&:hover': {
                          bgcolor: isDark ? alpha('#fff', 0.16) : alpha('#000', 0.12),
                        },
                      }
                    : {
                        bgcolor: 'transparent',
                        border: '1px solid',
                        borderColor: isDark ? alpha('#fff', 0.12) : alpha('#000', 0.1),
                        color: 'text.secondary',
                        '&:hover': {
                          bgcolor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.04),
                        },
                      }),
                }}
              />
            )
          })}
        </Box>
      </Box>

      {hasActiveFilters && (
        <Typography variant="caption" color="text.secondary" sx={{ pl: 0.5 }}>
          {t('settings.users.filter.showing', {
            count: filteredUserCount,
            total: totalUsers,
          })}
        </Typography>
      )}
    </Box>
  )
}
