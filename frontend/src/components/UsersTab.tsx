import React, { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Typography,
  Button,
  TextField,
  CircularProgress,
  Stack,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Chip,
  MenuItem,
  Select,
  FormControl,
  Tooltip,
  Divider,
  InputAdornment,
  alpha,
  useTheme,
} from '@mui/material'
import {
  Users,
  Trash2,
  Plus,
  Edit,
  Key,
  AlertCircle,
  ShieldCheck,
  UserCheck,
  Search,
} from 'lucide-react'
import { settingsAPI, repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { useAuth } from '../hooks/useAuth'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuthorization } from '../hooks/useAuthorization'
import { usePlan } from '../hooks/usePlan'
import { formatDateShort } from '../utils/dateUtils'
import { formatRoleLabel, getGlobalRolePresentation } from '../utils/rolePresentation'
import { translateBackendKey } from '../utils/translateBackendKey'
import { Column, ActionButton } from './DataTable'
import DataTable from './DataTable'
import UserPermissionsPanel from './UserPermissionsPanel'
import ResponsiveDialog from './ResponsiveDialog'

interface UserType {
  id: number
  username: string
  full_name?: string | null
  email: string
  is_active: boolean
  role: string
  all_repositories_role?: string | null
  auth_source?: string | null
  oidc_subject?: string | null
  created_at: string
  last_login: string | null
  // Legacy fields that may still appear in API responses
  profile_type?: string
  organization_name?: string
}

const getRoleAccentColor = (role: string): string => {
  if (role === 'admin' || role === 'superadmin') return '#7c3aed'
  if (role === 'operator') return '#0891b2'
  return '#059669'
}

const getInitials = (user: UserType): string => {
  if (user.full_name) {
    const parts = user.full_name.trim().split(/\s+/)
    return parts.length > 1
      ? `${parts[0][0]}${parts[1][0]}`.toUpperCase()
      : parts[0].slice(0, 2).toUpperCase()
  }
  return user.username.slice(0, 2).toUpperCase()
}

type RoleFilter = 'all' | 'admin' | 'operator' | 'viewer'
type StatusFilter = 'all' | 'active' | 'inactive' | 'pending_sso'

const UsersTab: React.FC = () => {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const { hasGlobalPermission } = useAuth()
  const { roleHasGlobalPermission } = useAuthorization()
  const { trackSettings, EventAction } = useAnalytics()
  const { can } = usePlan()
  const queryClient = useQueryClient()
  const canManageUsers = hasGlobalPermission('settings.users.manage')

  const getRolePresentation = useCallback((role: string) => getGlobalRolePresentation(role, t), [t])

  const getRepositoryAccessSummary = (user: UserType) => {
    if (getRolePresentation(user.role).isAdminRole) {
      return t('settings.users.accessSummary.adminRole')
    }
    if (user.all_repositories_role) {
      return t('settings.users.accessSummary.defaultAccess', {
        role: formatRoleLabel(user.all_repositories_role),
      })
    }
    return t('settings.users.accessSummary.restricted')
  }

  // Dialog / mutation state
  const [showCreateUser, setShowCreateUser] = useState(false)
  const [editingUser, setEditingUser] = useState<UserType | null>(null)
  const [showUserPasswordModal, setShowUserPasswordModal] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [accessUser, setAccessUser] = useState<UserType | null>(null)
  const [deleteConfirmUser, setDeleteConfirmUser] = useState<UserType | null>(null)

  const [userForm, setUserForm] = useState({
    username: '',
    email: '',
    password: '',
    role: 'viewer',
    full_name: '',
    auth_source: 'local',
    oidc_subject: '',
  })
  const [passwordForm, setPasswordForm] = useState({
    new_password: '',
  })

  // Search + filter state
  const [searchQuery, setSearchQuery] = useState('')
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  const { data: usersData, isLoading: loadingUsers } = useQuery({
    queryKey: ['users'],
    queryFn: settingsAPI.getUsers,
    enabled: canManageUsers,
  })

  const { data: repositoriesData } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
    enabled: canManageUsers,
  })

  const createUserMutation = useMutation({
    mutationFn: settingsAPI.createUser,
    onSuccess: () => {
      toast.success(t('settings.toasts.userCreated'))
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setShowCreateUser(false)
      trackSettings(EventAction.CREATE, {
        section: 'users',
        role: userForm.role,
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('settings.toasts.failedToCreateUser')
      )
    },
  })

  const updateUserMutation = useMutation({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mutationFn: ({ userId, userData }: { userId: number; userData: any }) =>
      settingsAPI.updateUser(userId, userData),
    onSuccess: () => {
      toast.success(t('settings.toasts.userUpdated'))
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setEditingUser(null)
      trackSettings(EventAction.EDIT, {
        section: 'users',
        role: userForm.role,
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('settings.toasts.failedToUpdateUser')
      )
    },
  })

  const deleteUserMutation = useMutation({
    mutationFn: settingsAPI.deleteUser,
    onSuccess: () => {
      toast.success(t('settings.toasts.userDeleted'))
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setDeleteConfirmUser(null)
      trackSettings(EventAction.DELETE, { section: 'users' })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('settings.toasts.failedToDeleteUser')
      )
    },
  })

  const approveUserMutation = useMutation({
    mutationFn: (userId: number) => settingsAPI.updateUser(userId, { is_active: true }),
    onSuccess: () => {
      toast.success(t('settings.toasts.userUpdated'))
      queryClient.invalidateQueries({ queryKey: ['users'] })
      trackSettings(EventAction.EDIT, {
        section: 'users',
        operation: 'approve_pending_oidc_user',
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('settings.toasts.failedToUpdateUser')
      )
    },
  })

  const resetPasswordMutation = useMutation({
    mutationFn: ({ userId, newPassword }: { userId: number; newPassword: string }) =>
      settingsAPI.resetUserPassword(userId, newPassword),
    onSuccess: () => {
      toast.success(t('settings.toasts.passwordReset'))
      setShowUserPasswordModal(false)
      setSelectedUserId(null)
      trackSettings(EventAction.EDIT, { section: 'users', operation: 'reset_password' })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('settings.toasts.failedToResetPassword')
      )
    },
  })

  const handleCreateUser = (e: React.FormEvent) => {
    e.preventDefault()
    createUserMutation.mutate({
      username: userForm.username,
      email: userForm.email,
      password: userForm.password,
      role: userForm.role,
      full_name: userForm.full_name,
    })
  }

  const handleUpdateUser = (e: React.FormEvent) => {
    e.preventDefault()
    if (editingUser) {
      const updatePayload: Record<string, unknown> = {
        username: userForm.username,
        email: userForm.email,
        password: userForm.password,
        role: userForm.role,
        full_name: userForm.full_name,
      }
      if (userOidcFieldsExposed) {
        updatePayload.auth_source = userForm.auth_source
        updatePayload.oidc_subject =
          userForm.auth_source === 'oidc' ? userForm.oidc_subject.trim() || null : null
      }
      updateUserMutation.mutate({
        userId: editingUser.id,
        userData: updatePayload,
      })
    }
  }

  const handleResetPassword = (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedUserId) {
      resetPasswordMutation.mutate({
        userId: selectedUserId,
        newPassword: passwordForm.new_password,
      })
    }
  }

  const handleDeleteUser = () => {
    if (deleteConfirmUser) {
      deleteUserMutation.mutate(deleteConfirmUser.id)
    }
  }

  const openPasswordModal = (userId: number) => {
    setSelectedUserId(userId)
    setShowUserPasswordModal(true)
    setPasswordForm({ new_password: '' })
  }

  const openEditUser = (userToEdit: UserType) => {
    setEditingUser(userToEdit)
    setUserForm({
      username: userToEdit.username,
      email: userToEdit.email,
      password: '',
      role: userToEdit.role || 'viewer',
      full_name: userToEdit.full_name || '',
      auth_source: userToEdit.auth_source || 'local',
      oidc_subject: userToEdit.oidc_subject || '',
    })
  }

  const openCreateUser = () => {
    setShowCreateUser(true)
    setUserForm({
      username: '',
      email: '',
      password: '',
      role: 'viewer',
      full_name: '',
      auth_source: 'local',
      oidc_subject: '',
    })
  }

  const users = useMemo<UserType[]>(() => usersData?.data?.users ?? [], [usersData?.data?.users])
  const userOidcFieldsExposed = users.some(
    (user) => 'auth_source' in user || 'oidc_subject' in user
  )

  const totalUsers = users.length
  const activeUsers = users.filter((u: UserType) => u.is_active).length
  const pendingSsoUsers = users.filter(
    (u: UserType) => !u.is_active && u.auth_source === 'oidc'
  ).length
  const adminUsers = users.filter((u: UserType) => getRolePresentation(u.role).isAdminRole).length
  const operatorUsers = users.filter(
    (u: UserType) => getRolePresentation(u.role).isOperatorRole
  ).length
  const viewerUsers = users.length - adminUsers - operatorUsers

  // Filtered users
  const filteredUsers = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return users.filter((user) => {
      if (q) {
        const haystack = [user.username, user.full_name ?? '', user.email, user.oidc_subject ?? '']
          .join(' ')
          .toLowerCase()
        if (!haystack.includes(q)) return false
      }
      if (roleFilter !== 'all') {
        const presentation = getRolePresentation(user.role)
        if (roleFilter === 'admin' && !presentation.isAdminRole) return false
        if (roleFilter === 'operator' && !presentation.isOperatorRole) return false
        if (roleFilter === 'viewer' && (presentation.isAdminRole || presentation.isOperatorRole))
          return false
      }
      if (statusFilter === 'active' && !user.is_active) return false
      if (statusFilter === 'inactive' && user.is_active) return false
      if (statusFilter === 'pending_sso' && (user.is_active || user.auth_source !== 'oidc')) {
        return false
      }
      return true
    })
  }, [users, searchQuery, roleFilter, statusFilter, getRolePresentation])

  // Keep selectedAccessUserId for backward compat with UserPermissionsPanel
  const [selectedAccessUserId, setSelectedAccessUserId] = useState<number | null>(null)
  useEffect(() => {
    if (accessUser) setSelectedAccessUserId(accessUser.id)
  }, [accessUser])

  // Table columns
  const columns: Column<UserType>[] = useMemo(
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

  // Table row actions
  const tableActions: ActionButton<UserType>[] = [
    {
      icon: <ShieldCheck size={15} />,
      label: t('settings.users.actions.approveSsoUser'),
      onClick: (user) => approveUserMutation.mutate(user.id),
      color: 'success',
      show: (user) => canManageUsers && !user.is_active && user.auth_source === 'oidc',
    },
    {
      icon: <UserCheck size={15} />,
      label: t('settings.users.actions.manageAccess'),
      onClick: (user) => setAccessUser(user),
      color: 'primary',
      show: () => canManageUsers,
    },
    {
      icon: <Edit size={15} />,
      label: t('settings.users.actions.edit'),
      onClick: (user) => openEditUser(user),
      color: 'default',
      show: () => canManageUsers,
    },
    {
      icon: <Key size={15} />,
      label: t('settings.users.actions.resetPassword'),
      onClick: (user) => openPasswordModal(user.id),
      color: 'warning',
      show: (user) => canManageUsers && user.auth_source !== 'oidc',
    },
    {
      icon: <Trash2 size={15} />,
      label: t('settings.users.actions.delete'),
      onClick: (user) => setDeleteConfirmUser(user),
      color: 'error',
      show: () => canManageUsers,
    },
  ]

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

  const hasActiveFilters =
    searchQuery.trim() !== '' || roleFilter !== 'all' || statusFilter !== 'all'

  return (
    <>
      <Stack spacing={3}>
        {/* Header */}
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
          <Tooltip title={!can('multi_user') ? t('settings.users.planCaption') : ''} arrow>
            <span>
              <Button
                variant="contained"
                startIcon={<Plus size={18} />}
                onClick={openCreateUser}
                disabled={!can('multi_user')}
                sx={{ width: { xs: '100%', sm: 'auto' } }}
              >
                {t('settings.users.addUser')}
              </Button>
            </span>
          </Tooltip>
        </Box>

        {/* Stat strip */}
        <Box sx={{ display: 'flex', gap: { xs: 3, sm: 4 }, flexWrap: 'wrap' }}>
          {[
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
          ].map((stat) => (
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

        {pendingSsoUsers > 0 && (
          <Alert
            severity="warning"
            action={
              <Button
                color="inherit"
                size="small"
                onClick={() => setStatusFilter('pending_sso')}
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
        )}

        {/* Search + filter toolbar */}
        {!loadingUsers && users.length > 0 && (
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
              {/* Search */}
              <TextField
                size="small"
                placeholder={t('settings.users.search.placeholder')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
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

              {/* Role filter chips */}
              <Box sx={{ display: 'flex', gap: 0.75, flexShrink: 0 }}>
                {roleFilterOptions.map((opt) => {
                  const isSelected = roleFilter === opt.value
                  const chipColor = opt.color
                  return (
                    <Chip
                      key={opt.value}
                      label={opt.label}
                      size="small"
                      onClick={() => setRoleFilter(opt.value)}
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

              {/* Status filter chips */}
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
                      onClick={() => setStatusFilter(opt.value)}
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

            {/* Result count */}
            {hasActiveFilters && (
              <Typography variant="caption" color="text.secondary" sx={{ pl: 0.5 }}>
                {t('settings.users.filter.showing', {
                  count: filteredUsers.length,
                  total: totalUsers,
                })}
              </Typography>
            )}
          </Box>
        )}

        {/* User table */}
        <DataTable<UserType>
          data={filteredUsers}
          columns={columns}
          actions={tableActions}
          getRowKey={(user) => user.id}
          loading={loadingUsers}
          defaultRowsPerPage={25}
          rowsPerPageOptions={[10, 25, 50, 100]}
          tableId="users-tab"
          emptyState={
            hasActiveFilters
              ? {
                  icon: <Search size={36} />,
                  title: t('settings.users.filter.noMatch'),
                  description: t('settings.users.filter.noMatchDescription'),
                }
              : {
                  icon: <Users size={36} />,
                  title: t('settings.users.emptyState.title'),
                  description: t('settings.users.emptyState.description'),
                }
          }
        />
      </Stack>

      {/* Repository Access Dialog */}
      <ResponsiveDialog
        open={!!accessUser}
        onClose={() => setAccessUser(null)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle sx={{ pb: 1 }}>
          <Typography variant="h6" fontWeight={600} lineHeight={1.2}>
            {t('settings.users.repositoryAccess.title')}
          </Typography>
          {accessUser && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {accessUser.full_name || accessUser.username}
            </Typography>
          )}
        </DialogTitle>
        <DialogContent>
          {accessUser && (
            <Stack spacing={2.5} sx={{ pt: 1, pb: 1 }}>
              <Box>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                  <ShieldCheck size={14} style={{ opacity: 0.6 }} />
                  <Typography variant="body2" fontWeight={600}>
                    {getRolePresentation(accessUser.role).label}
                  </Typography>
                </Stack>
                <Typography variant="body2" color="text.secondary">
                  {getRepositoryAccessSummary(accessUser)}
                </Typography>
              </Box>
              <Divider />
              {roleHasGlobalPermission(accessUser.role, 'repositories.manage_all') ? (
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1.5,
                    px: 2,
                    py: 1.75,
                    borderRadius: 2,
                    border: '1px solid',
                    borderColor: 'rgba(124,58,237,0.2)',
                    bgcolor: 'rgba(124,58,237,0.05)',
                  }}
                >
                  <ShieldCheck size={15} style={{ color: '#7c3aed', flexShrink: 0 }} />
                  <Box>
                    <Typography variant="body2" fontWeight={600}>
                      {t('settings.users.repositoryAccess.globalAccess')}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {t('settings.users.repositoryAccess.globalAccessDesc')}
                    </Typography>
                  </Box>
                </Box>
              ) : (
                <UserPermissionsPanel
                  userId={selectedAccessUserId ?? accessUser.id}
                  canManageAssignments={true}
                  repositories={repositoriesData?.data?.repositories ?? []}
                  targetUserRole={accessUser.role}
                />
              )}
            </Stack>
          )}
        </DialogContent>
      </ResponsiveDialog>

      {/* Create/Edit User Modal */}
      <Dialog
        open={showCreateUser || !!editingUser}
        onClose={() => {
          setShowCreateUser(false)
          setEditingUser(null)
        }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          {editingUser
            ? t('settings.users.editDialog.title')
            : t('settings.users.createDialog.title')}
        </DialogTitle>
        <form onSubmit={editingUser ? handleUpdateUser : handleCreateUser}>
          <DialogContent>
            <Stack spacing={3}>
              <TextField
                label={t('settings.users.fields.username')}
                value={userForm.username}
                onChange={(e) => setUserForm({ ...userForm, username: e.target.value })}
                required
                fullWidth
              />

              <TextField
                label={t('settings.users.fields.email')}
                type="email"
                value={userForm.email}
                onChange={(e) => setUserForm({ ...userForm, email: e.target.value })}
                required
                fullWidth
              />

              {!editingUser && (
                <TextField
                  label={t('settings.users.fields.password')}
                  type="password"
                  value={userForm.password}
                  onChange={(e) => setUserForm({ ...userForm, password: e.target.value })}
                  required
                  fullWidth
                />
              )}

              <TextField
                label={t('settings.users.fields.fullName')}
                value={userForm.full_name}
                onChange={(e) => setUserForm({ ...userForm, full_name: e.target.value })}
                fullWidth
              />

              <FormControl fullWidth>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                  {t('settings.users.fields.role')}
                </Typography>
                <Select
                  value={userForm.role}
                  onChange={(e) => setUserForm({ ...userForm, role: e.target.value })}
                  size="small"
                >
                  <MenuItem value="admin">{t('settings.users.roles.adminDescription')}</MenuItem>
                  <MenuItem value="operator">
                    {t('settings.users.roles.operatorDescription')}
                  </MenuItem>
                  <MenuItem value="viewer">{t('settings.users.roles.viewerDescription')}</MenuItem>
                </Select>
              </FormControl>

              {editingUser && userOidcFieldsExposed && (
                <>
                  <Alert severity="info">
                    <Typography variant="body2">
                      {t('settings.users.ssoIdentity.selfLinkHint')}
                    </Typography>
                  </Alert>
                  <Box
                    sx={{
                      display: 'grid',
                      gridTemplateColumns: { xs: '1fr', sm: '180px 1fr' },
                      gap: 2,
                    }}
                  >
                    <TextField
                      select
                      label={t('settings.users.fields.authSource')}
                      value={userForm.auth_source}
                      onChange={(e) =>
                        setUserForm({
                          ...userForm,
                          auth_source: e.target.value,
                          oidc_subject: e.target.value === 'oidc' ? userForm.oidc_subject : '',
                        })
                      }
                      fullWidth
                    >
                      <MenuItem value="local">{t('settings.users.authSources.local')}</MenuItem>
                      <MenuItem value="oidc">{t('settings.users.authSources.oidc')}</MenuItem>
                    </TextField>
                    <TextField
                      label={t('settings.users.fields.oidcSubject')}
                      value={userForm.oidc_subject}
                      onChange={(e) => setUserForm({ ...userForm, oidc_subject: e.target.value })}
                      disabled={userForm.auth_source !== 'oidc'}
                      helperText={
                        userForm.auth_source === 'oidc'
                          ? t('settings.users.ssoIdentity.subjectHelper')
                          : t('settings.users.ssoIdentity.clearHelper')
                      }
                      fullWidth
                    />
                  </Box>
                </>
              )}
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button
              onClick={() => {
                setShowCreateUser(false)
                setEditingUser(null)
              }}
            >
              {t('settings.users.buttons.cancel')}
            </Button>
            <Button type="submit" variant="contained">
              {editingUser
                ? t('settings.users.buttons.update')
                : t('settings.users.buttons.create')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Password Reset Modal */}
      <Dialog
        open={showUserPasswordModal}
        onClose={() => {
          setShowUserPasswordModal(false)
          setSelectedUserId(null)
        }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('settings.users.resetPasswordDialog.title')}</DialogTitle>
        <form onSubmit={handleResetPassword}>
          <DialogContent>
            <TextField
              label={t('settings.password.new')}
              type="password"
              value={passwordForm.new_password}
              onChange={(e) => setPasswordForm({ new_password: e.target.value })}
              required
              fullWidth
            />
          </DialogContent>
          <DialogActions>
            <Button
              onClick={() => {
                setShowUserPasswordModal(false)
                setSelectedUserId(null)
              }}
            >
              {t('settings.users.buttons.cancel')}
            </Button>
            <Button type="submit" variant="contained">
              {t('settings.users.actions.resetPassword')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Delete User Confirmation Dialog */}
      <Dialog
        open={!!deleteConfirmUser}
        onClose={() => setDeleteConfirmUser(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>
          <Stack direction="row" spacing={2} alignItems="center">
            <Box
              sx={{
                width: 48,
                height: 48,
                borderRadius: '50%',
                backgroundColor: 'error.lighter',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <AlertCircle size={24} color="#d32f2f" />
            </Box>
            <Typography variant="h6" fontWeight={600}>
              {t('settings.users.deleteDialog.title')}
            </Typography>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            {t('settings.users.deleteDialog.message', { username: deleteConfirmUser?.username })}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {t('settings.users.deleteDialog.warning')}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteConfirmUser(null)}>
            {t('settings.users.buttons.cancel')}
          </Button>
          <Button
            onClick={handleDeleteUser}
            variant="contained"
            color="error"
            disabled={deleteUserMutation.isPending}
            startIcon={deleteUserMutation.isPending ? <CircularProgress size={16} /> : null}
          >
            {deleteUserMutation.isPending
              ? t('settings.users.deleteDialog.deleting')
              : t('settings.users.deleteDialog.confirm')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  )
}

export default UsersTab
