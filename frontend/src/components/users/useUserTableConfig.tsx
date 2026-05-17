import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Box, Chip, Stack, Tooltip, Typography, alpha } from '@mui/material'
import { Edit, Key, ShieldCheck, Trash2, UserCheck } from 'lucide-react'
import { ActionButton, Column } from '../DataTable'
import { formatDateShort } from '../../utils/dateUtils'
import { UserType } from './types'
import { getInitials, getRoleAccentColor } from './userPresentation'

type RolePresentation = {
  label: string
  color: 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning'
  isAdminRole: boolean
  isOperatorRole: boolean
}

interface UseUserTableColumnsParams {
  isDark: boolean
  getRolePresentation: (role: string) => RolePresentation
}

export const useUserTableColumns = ({
  isDark,
  getRolePresentation,
}: UseUserTableColumnsParams): Column<UserType>[] => {
  const { t } = useTranslation()

  return useMemo(
    () => [
      {
        id: 'user',
        label: t('settings.users.table.user'),
        render: (user) => {
          const accent = getRoleAccentColor(user.role)
          return (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 0.25 }}>
              <Box
                sx={{
                  width: 34,
                  height: 34,
                  borderRadius: '50%',
                  bgcolor: alpha(accent, isDark ? 0.2 : 0.12),
                  border: '1.5px solid',
                  borderColor: alpha(accent, isDark ? 0.45 : 0.35),
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <Typography
                  sx={{ fontSize: '0.64rem', fontWeight: 800, color: accent, lineHeight: 1 }}
                >
                  {getInitials(user)}
                </Typography>
              </Box>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="body2" fontWeight={600} noWrap>
                  {user.full_name || user.username}
                </Typography>
                <Stack spacing={0.4} sx={{ minWidth: 0 }}>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    noWrap
                    sx={{ display: 'block', lineHeight: 1.4 }}
                  >
                    {user.email || `@${user.username}`}
                  </Typography>
                  {(user.auth_source === 'oidc' || user.oidc_subject) && (
                    <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0 }}>
                      {user.auth_source === 'oidc' && (
                        <Chip
                          size="small"
                          variant="outlined"
                          color="info"
                          label={t('settings.users.badges.oidc')}
                          sx={{ height: 20 }}
                        />
                      )}
                      {user.oidc_subject && (
                        <Tooltip title={user.oidc_subject}>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            noWrap
                            sx={{ display: 'block', minWidth: 0 }}
                          >
                            {t('settings.users.labels.subject', { subject: user.oidc_subject })}
                          </Typography>
                        </Tooltip>
                      )}
                    </Stack>
                  )}
                </Stack>
              </Box>
            </Box>
          )
        },
      },
      {
        id: 'role',
        label: t('settings.users.table.role'),
        width: '110px',
        render: (user) => {
          const rolePresentation = getRolePresentation(user.role)
          return <Chip label={rolePresentation.label} color={rolePresentation.color} size="small" />
        },
      },
      {
        id: 'status',
        label: t('settings.users.table.status'),
        width: '100px',
        render: (user) => (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
            <Box
              sx={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                bgcolor: user.is_active ? 'success.main' : 'error.main',
                flexShrink: 0,
              }}
            />
            <Typography
              variant="body2"
              sx={{
                color: user.is_active ? 'success.main' : 'error.main',
                fontWeight: 500,
                fontSize: '0.8rem',
              }}
            >
              {user.is_active
                ? t('settings.users.status.active')
                : user.auth_source === 'oidc'
                  ? t('settings.users.status.pendingSso')
                  : t('settings.users.status.inactive')}
            </Typography>
            {!user.is_active && user.auth_source === 'oidc' && (
              <Chip
                size="small"
                color="warning"
                variant="outlined"
                label={t('settings.users.badges.sso')}
              />
            )}
          </Box>
        ),
      },
      {
        id: 'created',
        label: t('settings.users.table.created'),
        width: '110px',
        render: (user) => (
          <Typography variant="body2" color="text.secondary">
            {formatDateShort(user.created_at)}
          </Typography>
        ),
      },
      {
        id: 'lastLogin',
        label: t('settings.users.table.lastLogin'),
        width: '120px',
        render: (user) => (
          <Typography variant="body2" color="text.secondary">
            {user.last_login ? formatDateShort(user.last_login) : t('common.never')}
          </Typography>
        ),
      },
    ],
    [t, isDark, getRolePresentation]
  )
}

interface UseUserTableActionsParams {
  canManageUsers: boolean
  onApproveSsoUser: (user: UserType) => void
  onManageAccess: (user: UserType) => void
  onEditUser: (user: UserType) => void
  onResetPassword: (userId: number) => void
  onDeleteUser: (user: UserType) => void
}

export const useUserTableActions = ({
  canManageUsers,
  onApproveSsoUser,
  onManageAccess,
  onEditUser,
  onResetPassword,
  onDeleteUser,
}: UseUserTableActionsParams): ActionButton<UserType>[] => {
  const { t } = useTranslation()

  return useMemo(
    () => [
      {
        icon: <ShieldCheck size={15} />,
        label: t('settings.users.actions.approveSsoUser'),
        onClick: onApproveSsoUser,
        color: 'success',
        show: (user) => canManageUsers && !user.is_active && user.auth_source === 'oidc',
      },
      {
        icon: <UserCheck size={15} />,
        label: t('settings.users.actions.manageAccess'),
        onClick: onManageAccess,
        color: 'primary',
        show: () => canManageUsers,
      },
      {
        icon: <Edit size={15} />,
        label: t('settings.users.actions.edit'),
        onClick: onEditUser,
        color: 'default',
        show: () => canManageUsers,
      },
      {
        icon: <Key size={15} />,
        label: t('settings.users.actions.resetPassword'),
        onClick: (user) => onResetPassword(user.id),
        color: 'warning',
        show: (user) => canManageUsers && user.auth_source !== 'oidc',
      },
      {
        icon: <Trash2 size={15} />,
        label: t('settings.users.actions.delete'),
        onClick: onDeleteUser,
        color: 'error',
        show: () => canManageUsers,
      },
    ],
    [t, canManageUsers, onApproveSsoUser, onManageAccess, onEditUser, onResetPassword, onDeleteUser]
  )
}
