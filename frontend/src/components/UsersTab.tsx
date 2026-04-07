import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Typography,
  Button,
  TextField,
  CircularProgress,
  Stack,
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
} from '@mui/material'
import { Users, Trash2, Plus, Edit, Key, AlertCircle, ShieldCheck, UserCheck } from 'lucide-react'
import { settingsAPI, repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { useAuth } from '../hooks/useAuth'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuthorization } from '../hooks/useAuthorization'
import { usePlan } from '../hooks/usePlan'
import { formatDateShort } from '../utils/dateUtils'
import { formatRoleLabel, getGlobalRolePresentation } from '../utils/rolePresentation'
import { translateBackendKey } from '../utils/translateBackendKey'
import EntityCard, { StatItem, ActionItem } from './EntityCard'
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

const UsersTab: React.FC = () => {
  const { t } = useTranslation()
  const { hasGlobalPermission } = useAuth()
  const { roleHasGlobalPermission } = useAuthorization()
  const { trackSettings, EventAction } = useAnalytics()
  const { can } = usePlan()
  const queryClient = useQueryClient()
  const canManageUsers = hasGlobalPermission('settings.users.manage')

  const getRolePresentation = (role: string) => {
    return getGlobalRolePresentation(role, t)
  }

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
  })
  const [passwordForm, setPasswordForm] = useState({
    new_password: '',
  })

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
    createUserMutation.mutate(userForm)
  }

  const handleUpdateUser = (e: React.FormEvent) => {
    e.preventDefault()
    if (editingUser) {
      updateUserMutation.mutate({
        userId: editingUser.id,
        userData: userForm,
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
    })
  }

  const users = React.useMemo<UserType[]>(
    () => usersData?.data?.users ?? [],
    [usersData?.data?.users]
  )

  const totalUsers = users.length
  const activeUsers = users.filter((u: UserType) => u.is_active).length
  const adminUsers = users.filter((u: UserType) => getRolePresentation(u.role).isAdminRole).length
  const operatorUsers = users.filter(
    (u: UserType) => getRolePresentation(u.role).isOperatorRole
  ).length
  const viewerUsers = users.length - adminUsers - operatorUsers

  // Keep selectedAccessUserId for backward compat with UserPermissionsPanel
  const [selectedAccessUserId, setSelectedAccessUserId] = useState<number | null>(null)
  useEffect(() => {
    if (accessUser) setSelectedAccessUserId(accessUser.id)
  }, [accessUser])

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

        {/* Compact stat strip */}
        <Box sx={{ display: 'flex', gap: { xs: 3, sm: 4 }, flexWrap: 'wrap' }}>
          {[
            { label: t('settings.users.stats.total'), value: totalUsers, color: 'text.primary' },
            { label: t('settings.users.stats.active'), value: activeUsers, color: 'success.main' },
            {
              label: t('settings.users.stats.admins'),
              value: adminUsers,
              color: 'secondary.main',
            },
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

        {/* User list */}
        <Box>
          {loadingUsers ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
              <CircularProgress />
            </Box>
          ) : users.length === 0 ? (
            <Box sx={{ py: 6, textAlign: 'center', color: 'text.secondary' }}>
              <Users size={40} style={{ opacity: 0.25, marginBottom: 12 }} />
              <Typography variant="body1" gutterBottom>
                {t('settings.users.emptyState.title')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t('settings.users.emptyState.description')}
              </Typography>
            </Box>
          ) : (
            <Stack spacing={2}>
              {users.map((user: UserType) => {
                const rolePresentation = getRolePresentation(user.role)
                const displayName = user.full_name || user.username

                const stats: StatItem[] = [
                  {
                    icon: (
                      <Box
                        sx={{
                          width: 7,
                          height: 7,
                          borderRadius: '50%',
                          bgcolor: user.is_active ? 'success.main' : 'error.main',
                          mt: '1px',
                        }}
                      />
                    ),
                    label: t('settings.users.statLabels.status'),
                    value: user.is_active
                      ? t('settings.users.status.active')
                      : t('settings.users.status.inactive'),
                  },
                  {
                    icon: null,
                    label: t('settings.users.statLabels.joined'),
                    value: formatDateShort(user.created_at),
                  },
                  {
                    icon: null,
                    label: t('settings.users.statLabels.lastLogin'),
                    value: user.last_login ? formatDateShort(user.last_login) : t('common.never'),
                  },
                ]

                const actions: ActionItem[] = [
                  {
                    icon: <Edit size={16} />,
                    tooltip: t('settings.users.actions.edit'),
                    onClick: () => openEditUser(user),
                    color: 'primary',
                    hidden: !canManageUsers,
                  },
                  {
                    icon: <Key size={16} />,
                    tooltip: t('settings.users.actions.resetPassword'),
                    onClick: () => openPasswordModal(user.id),
                    color: 'warning',
                    hidden: !canManageUsers,
                  },
                  {
                    icon: <Trash2 size={16} />,
                    tooltip: t('settings.users.actions.delete'),
                    onClick: () => setDeleteConfirmUser(user),
                    color: 'error',
                    hidden: !canManageUsers,
                  },
                ]

                const badge = (
                  <Chip
                    label={rolePresentation.label}
                    color={rolePresentation.color}
                    size="small"
                  />
                )

                return (
                  <EntityCard
                    key={user.id}
                    title={displayName}
                    subtitle={`@${user.username}${user.email ? ` · ${user.email}` : ''}`}
                    badge={badge}
                    stats={stats}
                    actions={actions}
                    primaryAction={
                      canManageUsers
                        ? {
                            label: t('settings.users.actions.manageAccess'),
                            icon: <UserCheck size={13} />,
                            onClick: () => setAccessUser(user),
                            color: '#6366f1',
                          }
                        : undefined
                    }
                    accentColor={getRoleAccentColor(user.role)}
                  />
                )
              })}
            </Stack>
          )}
        </Box>
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
