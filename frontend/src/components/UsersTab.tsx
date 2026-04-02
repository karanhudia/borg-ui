import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Card,
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
  Tabs,
  Tab,
} from '@mui/material'
import { Users, Trash2, Plus, Edit, Key, AlertCircle, ShieldCheck } from 'lucide-react'
import { settingsAPI, repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { useAuth } from '../hooks/useAuth'
import { useAnalytics } from '../hooks/useAnalytics'
import { usePlan } from '../hooks/usePlan'
import { formatDateShort } from '../utils/dateUtils'
import { translateBackendKey } from '../utils/translateBackendKey'
import DataTable, { Column, ActionButton } from './DataTable'
import UserPermissionsPanel from './UserPermissionsPanel'

interface UserType {
  id: number
  username: string
  full_name?: string | null
  email: string
  is_active: boolean
  role: string
  created_at: string
  last_login: string | null
  // Legacy fields that may still appear in API responses
  profile_type?: string
  organization_name?: string
}

const UsersTab: React.FC = () => {
  const { t } = useTranslation()
  const { isAdmin } = useAuth()
  const { trackSettings, EventAction } = useAnalytics()
  const { can } = usePlan()
  const queryClient = useQueryClient()

  const [usersView, setUsersView] = useState<'directory' | 'access'>('directory')
  const [showCreateUser, setShowCreateUser] = useState(false)
  const [editingUser, setEditingUser] = useState<UserType | null>(null)
  const [showUserPasswordModal, setShowUserPasswordModal] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [selectedAccessUserId, setSelectedAccessUserId] = useState<number | null>(null)
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
    enabled: isAdmin,
  })

  const { data: repositoriesData } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
    enabled: isAdmin,
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

  const userColumns: Column<UserType>[] = [
    {
      id: 'user',
      label: t('settings.users.table.user'),
      render: (u) => (
        <Box>
          <Typography variant="body2" fontWeight={500}>
            {u.full_name || u.username}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            @{u.username}
            {u.email ? ` • ${u.email}` : ''}
          </Typography>
        </Box>
      ),
    },
    {
      id: 'status',
      label: t('settings.users.table.status'),
      render: (u) => (
        <Chip
          label={
            u.is_active ? t('settings.users.status.active') : t('settings.users.status.inactive')
          }
          color={u.is_active ? 'success' : 'error'}
          size="small"
        />
      ),
    },
    {
      id: 'role',
      label: t('settings.users.table.role'),
      render: (u) => (
        <Chip
          label={
            u.role === 'admin'
              ? t('settings.users.roles.admin')
              : u.role === 'operator'
                ? t('settings.users.roles.operator')
                : t('settings.users.roles.viewer')
          }
          color={u.role === 'admin' ? 'secondary' : u.role === 'operator' ? 'info' : 'default'}
          size="small"
        />
      ),
    },
    {
      id: 'created_at',
      label: t('settings.users.table.created'),
      render: (u) => <Typography variant="body2">{formatDateShort(u.created_at)}</Typography>,
    },
    {
      id: 'last_login',
      label: t('settings.users.table.lastLogin'),
      render: (u) => (
        <Typography variant="body2" color="text.secondary">
          {formatDateShort(u.last_login)}
        </Typography>
      ),
    },
  ]

  const userActions: ActionButton<UserType>[] = [
    {
      icon: <Edit size={16} />,
      label: t('settings.users.actions.edit'),
      onClick: openEditUser,
      color: 'primary',
      tooltip: t('settings.users.actions.edit'),
    },
    {
      icon: <Key size={16} />,
      label: t('settings.users.actions.resetPassword'),
      onClick: (u) => openPasswordModal(u.id),
      color: 'warning',
      tooltip: t('settings.users.actions.resetPassword'),
    },
    {
      icon: <Trash2 size={16} />,
      label: t('settings.users.actions.delete'),
      onClick: setDeleteConfirmUser,
      color: 'error',
      tooltip: t('settings.users.actions.delete'),
    },
  ]

  const users = usersData?.data?.users || []
  const selectedAccessUser =
    users.find((account: UserType) => account.id === selectedAccessUserId) ?? users[0] ?? null
  const totalUsers = users.length
  const activeUsers = users.filter((account: UserType) => account.is_active).length
  const adminUsers = users.filter((account: UserType) => account.role === 'admin').length
  const operatorUsers = users.filter((account: UserType) => account.role === 'operator').length
  const viewerUsers = users.filter((account: UserType) => account.role === 'viewer').length

  useEffect(() => {
    if (!selectedAccessUserId && users.length > 0) {
      setSelectedAccessUserId(users[0].id)
    }
  }, [selectedAccessUserId, users])

  return (
    <>
      <Stack spacing={3}>
        <Card variant="outlined" sx={{ borderRadius: 3, overflow: 'hidden' }}>
          <Box
            sx={{
              px: { xs: 2.5, md: 3.5 },
              py: { xs: 2.5, md: 3 },
              background:
                'linear-gradient(180deg, rgba(23,23,23,0.03) 0%, rgba(23,23,23,0.00) 100%)',
            }}
          >
            <Stack
              direction={{ xs: 'column', md: 'row' }}
              spacing={2}
              justifyContent="space-between"
              alignItems={{ xs: 'flex-start', md: 'center' }}
            >
              <Box>
                <Typography variant="h5" fontWeight={700} gutterBottom>
                  {t('settings.users.title')}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Manage account records and repository-level access from one admin surface.
                </Typography>
              </Box>
              <Tooltip title={!can('multi_user') ? t('settings.users.planCaption') : ''} arrow>
                <span>
                  <Button
                    variant="contained"
                    startIcon={<Plus size={18} />}
                    onClick={openCreateUser}
                    disabled={!can('multi_user')}
                  >
                    {t('settings.users.addUser')}
                  </Button>
                </span>
              </Tooltip>
            </Stack>
          </Box>
        </Card>

        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: {
              xs: '1fr',
              sm: 'repeat(2, minmax(0, 1fr))',
              lg: 'repeat(4, minmax(0, 1fr))',
            },
            gap: 2,
          }}
        >
          {[
            { label: 'Total users', value: totalUsers, tone: 'primary.main' },
            { label: 'Active', value: activeUsers, tone: 'success.main' },
            { label: 'Admins', value: adminUsers, tone: 'secondary.main' },
            {
              label: 'Operators / Viewers',
              value: `${operatorUsers} / ${viewerUsers}`,
              tone: 'info.main',
            },
          ].map((stat) => (
            <Card key={stat.label} variant="outlined" sx={{ borderRadius: 3 }}>
              <Box sx={{ p: 2.5 }}>
                <Typography variant="caption" color="text.secondary">
                  {stat.label}
                </Typography>
                <Typography variant="h5" fontWeight={700} sx={{ color: stat.tone, mt: 0.5 }}>
                  {stat.value}
                </Typography>
              </Box>
            </Card>
          ))}
        </Box>

        <Card variant="outlined" sx={{ borderRadius: 3, overflow: 'hidden' }}>
          <Box sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
            <Tabs
              value={usersView}
              onChange={(_, value) => {
                setUsersView(value)
                trackSettings(EventAction.VIEW, { section: 'users', surface: value })
              }}
              variant="scrollable"
              scrollButtons="auto"
              sx={{ px: { xs: 1, md: 2 } }}
            >
              <Tab
                value="directory"
                label="Directory"
                sx={{ minHeight: 48, textTransform: 'none', fontWeight: 600 }}
              />
              <Tab
                value="access"
                label="Repository access"
                sx={{ minHeight: 48, textTransform: 'none', fontWeight: 600 }}
              />
            </Tabs>
          </Box>
          <Box sx={{ p: { xs: 2, md: 2.5 } }}>
            {usersView === 'directory' && (
              <DataTable
                data={users}
                columns={userColumns}
                actions={userActions}
                getRowKey={(u) => u.id}
                loading={loadingUsers}
                emptyState={{
                  icon: <Users size={48} />,
                  title: t('settings.users.emptyState.title'),
                  description: t('settings.users.emptyState.description'),
                }}
                variant="outlined"
                tableId="settings-users"
              />
            )}

            {usersView === 'access' && (
              <Box
                sx={{
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 2.5,
                  overflow: 'hidden',
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', md: '220px 1fr' },
                  minHeight: 320,
                }}
              >
                {/* Left: User list */}
                <Box
                  sx={{
                    borderRight: { md: '1px solid' },
                    borderBottom: { xs: '1px solid', md: 'none' },
                    borderColor: 'divider',
                    bgcolor: 'action.hover',
                  }}
                >
                  <Box
                    sx={{
                      px: 2,
                      py: 1.25,
                      borderBottom: '1px solid',
                      borderColor: 'divider',
                    }}
                  >
                    <Typography
                      variant="caption"
                      fontWeight={700}
                      color="text.secondary"
                      sx={{
                        letterSpacing: '0.06em',
                        textTransform: 'uppercase',
                        fontSize: '0.68rem',
                      }}
                    >
                      Users
                    </Typography>
                  </Box>
                  {users.map((account: UserType) => {
                    const displayName = account.full_name || account.username
                    const isSelected = selectedAccessUser?.id === account.id
                    return (
                      <Box
                        key={account.id}
                        onClick={() => {
                          setSelectedAccessUserId(account.id)
                          trackSettings(EventAction.VIEW, {
                            section: 'users',
                            operation: 'select_access_user',
                            user_role: account.role,
                          })
                        }}
                        sx={{
                          px: 2,
                          py: 1.5,
                          cursor: 'pointer',
                          borderLeft: '2px solid',
                          borderColor: isSelected ? '#059669' : 'transparent',
                          bgcolor: isSelected ? 'rgba(5,150,105,0.07)' : 'transparent',
                          '&:not(:last-child)': {
                            borderBottom: '1px solid',
                            borderColor: 'divider',
                          },
                          '&:hover': {
                            bgcolor: isSelected ? 'rgba(5,150,105,0.07)' : 'rgba(255,255,255,0.03)',
                          },
                          transition: 'background-color 150ms ease, border-color 150ms ease',
                        }}
                      >
                        <Stack direction="row" spacing={1.5} alignItems="center">
                          <Box
                            sx={{
                              width: 28,
                              height: 28,
                              borderRadius: '50%',
                              flexShrink: 0,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              background: isSelected
                                ? 'linear-gradient(135deg, #059669 0%, #047857 100%)'
                                : 'linear-gradient(135deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.04) 100%)',
                              border: '1px solid',
                              borderColor: isSelected
                                ? 'rgba(5,150,105,0.4)'
                                : 'rgba(255,255,255,0.08)',
                              transition: 'all 150ms ease',
                            }}
                          >
                            <Typography
                              sx={{
                                fontSize: '0.7rem',
                                fontWeight: 700,
                                color: isSelected ? '#fff' : 'text.secondary',
                                lineHeight: 1,
                              }}
                            >
                              {account.username.charAt(0).toUpperCase()}
                            </Typography>
                          </Box>
                          <Box sx={{ minWidth: 0 }}>
                            <Typography
                              variant="body2"
                              fontWeight={isSelected ? 700 : 500}
                              noWrap
                              sx={{
                                color: isSelected ? '#34d399' : 'text.primary',
                                fontSize: '0.8rem',
                              }}
                            >
                              {displayName}
                            </Typography>
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              noWrap
                              sx={{ fontSize: '0.72rem' }}
                            >
                              {account.role}
                            </Typography>
                          </Box>
                        </Stack>
                      </Box>
                    )
                  })}
                </Box>

                {/* Right: Permissions panel */}
                {selectedAccessUser ? (
                  <Box>
                    <Box
                      sx={{
                        px: 2.5,
                        py: 2,
                        borderBottom: '1px solid',
                        borderColor: 'divider',
                        bgcolor: 'action.hover',
                      }}
                    >
                      <Stack direction="row" spacing={1.25} alignItems="center" sx={{ mb: 0.25 }}>
                        <ShieldCheck size={15} style={{ opacity: 0.6, flexShrink: 0 }} />
                        <Typography variant="body2" fontWeight={700}>
                          {selectedAccessUser.profile_type === 'enterprise'
                            ? selectedAccessUser.organization_name ||
                              selectedAccessUser.full_name ||
                              selectedAccessUser.username
                            : selectedAccessUser.full_name ||
                              selectedAccessUser.organization_name ||
                              selectedAccessUser.username}
                        </Typography>
                        <Chip
                          size="small"
                          label={selectedAccessUser.role}
                          color={
                            selectedAccessUser.role === 'admin'
                              ? 'error'
                              : selectedAccessUser.role === 'operator'
                                ? 'info'
                                : 'default'
                          }
                          sx={{ ml: 'auto !important', height: 20, fontSize: '0.7rem' }}
                        />
                      </Stack>
                      <Typography variant="caption" color="text.secondary">
                        {selectedAccessUser.role === 'admin'
                          ? 'Admin role grants full access to all repositories.'
                          : 'Assign or remove repository-level access for this user.'}
                      </Typography>
                    </Box>
                    <Box sx={{ p: 2.5 }}>
                      {selectedAccessUser.role === 'admin' ? (
                        <Box
                          sx={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 1.5,
                            px: 2,
                            py: 1.75,
                            borderRadius: 2,
                            border: '1px solid',
                            borderColor: 'rgba(248,113,113,0.2)',
                            bgcolor: 'rgba(239,68,68,0.05)',
                          }}
                        >
                          <ShieldCheck size={15} style={{ color: '#f87171', flexShrink: 0 }} />
                          <Box>
                            <Typography variant="body2" fontWeight={600}>
                              Global access
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              Admin accounts inherit full access to all repositories — no
                              per-repository grants needed.
                            </Typography>
                          </Box>
                        </Box>
                      ) : (
                        <UserPermissionsPanel
                          userId={selectedAccessUser.id}
                          isAdmin={true}
                          repositories={repositoriesData?.data?.repositories ?? []}
                          targetUserRole={selectedAccessUser.role}
                        />
                      )}
                    </Box>
                  </Box>
                ) : (
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      p: 4,
                      color: 'text.secondary',
                    }}
                  >
                    <Typography variant="body2">
                      Select a user to manage their repository access
                    </Typography>
                  </Box>
                )}
              </Box>
            )}
          </Box>
        </Card>
      </Stack>

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
                label="Full name"
                value={userForm.full_name}
                onChange={(e) => setUserForm({ ...userForm, full_name: e.target.value })}
                fullWidth
              />

              <FormControl fullWidth>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                  Role
                </Typography>
                <Select
                  value={userForm.role}
                  onChange={(e) => setUserForm({ ...userForm, role: e.target.value })}
                  size="small"
                >
                  <MenuItem value="admin">
                    Admin — Full access to all features and settings
                  </MenuItem>
                  <MenuItem value="operator">
                    Operator — Can run backups, manage schedules. Cannot manage users or system
                    settings
                  </MenuItem>
                  <MenuItem value="viewer">Viewer — Read-only access</MenuItem>
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
