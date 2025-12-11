import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
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
  FormControlLabel,
  Checkbox,
  MenuItem,
  Select,
  FormControl,
} from '@mui/material'
import { Users, Trash2, Plus, Edit, Key, AlertCircle, Moon, Sun } from 'lucide-react'
import { settingsAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { useAuth } from '../hooks/useAuth'
import { useTheme } from '../context/ThemeContext'
import { availableThemes } from '../theme'
import NotificationsTab from '../components/NotificationsTab'
import PackagesTab from '../components/PackagesTab'
import ExportImportTab from '../components/ExportImportTab'
import Scripts from './Scripts'
import Activity from './Activity'
import { formatDateShort } from '../utils/dateUtils'
import DataTable, { Column, ActionButton } from '../components/DataTable'

interface UserType {
  id: number
  username: string
  email: string
  is_active: boolean
  is_admin: boolean
  created_at: string
  last_login: string | null
}

const Settings: React.FC = () => {
  const { user } = useAuth()
  const { mode, setTheme } = useTheme()
  const queryClient = useQueryClient()
  const { tab } = useParams<{ tab?: string }>()

  // Get tab order based on user role
  const getTabOrder = () => {
    const baseTabs = ['account', 'appearance', 'notifications']
    if (user?.is_admin) {
      return [...baseTabs, 'packages', 'scripts', 'export', 'users', 'activity']
    }
    return [...baseTabs, 'scripts', 'export', 'activity']
  }

  // Determine active tab from URL or default to 'account'
  const getTabIndexFromPath = (tabPath?: string): number => {
    if (!tabPath) return 0
    const tabOrder = getTabOrder()
    const index = tabOrder.indexOf(tabPath)
    return index >= 0 ? index : 0
  }

  const [activeTab, setActiveTab] = useState(getTabIndexFromPath(tab))

  // Update active tab when URL changes
  useEffect(() => {
    setActiveTab(getTabIndexFromPath(tab))
  }, [tab])
  const [showCreateUser, setShowCreateUser] = useState(false)
  const [editingUser, setEditingUser] = useState<UserType | null>(null)
  const [showPasswordModal, setShowPasswordModal] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [deleteConfirmUser, setDeleteConfirmUser] = useState<UserType | null>(null)
  const [changePasswordForm, setChangePasswordForm] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  })

  // Change password mutation (for current user)
  const changePasswordMutation = useMutation({
    mutationFn: (passwordData: { current_password: string; new_password: string }) =>
      settingsAPI.changePassword(passwordData),
    onSuccess: () => {
      toast.success('Password changed successfully')
      setChangePasswordForm({ current_password: '', new_password: '', confirm_password: '' })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to change password')
    },
  })

  // Users
  const { data: usersData, isLoading: loadingUsers } = useQuery({
    queryKey: ['users'],
    queryFn: settingsAPI.getUsers,
    enabled: user?.is_admin === true,
  })

  const createUserMutation = useMutation({
    mutationFn: settingsAPI.createUser,
    onSuccess: () => {
      toast.success('User created successfully')
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setShowCreateUser(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create user')
    },
  })

  const updateUserMutation = useMutation({
    mutationFn: ({ userId, userData }: { userId: number; userData: any }) =>
      settingsAPI.updateUser(userId, userData),
    onSuccess: () => {
      toast.success('User updated successfully')
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setEditingUser(null)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update user')
    },
  })

  const deleteUserMutation = useMutation({
    mutationFn: settingsAPI.deleteUser,
    onSuccess: () => {
      toast.success('User deleted successfully')
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setDeleteConfirmUser(null)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete user')
    },
  })

  const resetPasswordMutation = useMutation({
    mutationFn: ({ userId, newPassword }: { userId: number; newPassword: string }) =>
      settingsAPI.resetUserPassword(userId, newPassword),
    onSuccess: () => {
      toast.success('Password reset successfully')
      setShowPasswordModal(false)
      setSelectedUserId(null)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to reset password')
    },
  })

  // Form states
  const [userForm, setUserForm] = useState({
    username: '',
    email: '',
    password: '',
    is_admin: false,
  })
  const [passwordForm, setPasswordForm] = useState({
    new_password: '',
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
    setShowPasswordModal(true)
    setPasswordForm({ new_password: '' })
  }

  const openEditUser = (user: UserType) => {
    setEditingUser(user)
    setUserForm({
      username: user.username,
      email: user.email,
      password: '',
      is_admin: user.is_admin,
    })
  }

  const openCreateUser = () => {
    setShowCreateUser(true)
    setUserForm({
      username: '',
      email: '',
      password: '',
      is_admin: false,
    })
  }

  // Column definitions for Users table
  const userColumns: Column<UserType>[] = [
    {
      id: 'user',
      label: 'User',
      render: (user) => (
        <Box>
          <Typography variant="body2" fontWeight={500}>
            {user.username}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {user.email}
          </Typography>
        </Box>
      ),
    },
    {
      id: 'status',
      label: 'Status',
      render: (user) => (
        <Chip
          label={user.is_active ? 'Active' : 'Inactive'}
          color={user.is_active ? 'success' : 'error'}
          size="small"
        />
      ),
    },
    {
      id: 'role',
      label: 'Role',
      render: (user) => (
        <Chip
          label={user.is_admin ? 'Admin' : 'User'}
          color={user.is_admin ? 'secondary' : 'default'}
          size="small"
        />
      ),
    },
    {
      id: 'created_at',
      label: 'Created',
      render: (user) => <Typography variant="body2">{formatDateShort(user.created_at)}</Typography>,
    },
    {
      id: 'last_login',
      label: 'Last Login',
      render: (user) => (
        <Typography variant="body2" color="text.secondary">
          {formatDateShort(user.last_login)}
        </Typography>
      ),
    },
  ]

  // Action buttons for Users table
  const userActions: ActionButton<UserType>[] = [
    {
      icon: <Edit size={16} />,
      label: 'Edit User',
      onClick: openEditUser,
      color: 'primary',
      tooltip: 'Edit User',
    },
    {
      icon: <Key size={16} />,
      label: 'Reset Password',
      onClick: (user) => openPasswordModal(user.id),
      color: 'warning',
      tooltip: 'Reset Password',
    },
    {
      icon: <Trash2 size={16} />,
      label: 'Delete User',
      onClick: setDeleteConfirmUser,
      color: 'error',
      tooltip: 'Delete User',
    },
  ]

  return (
    <Box>
      {/* Content is controlled by sidebar navigation */}

      {/* Profile Tab */}
      {activeTab === 0 && (
        <Box>
          <Box>
            <Typography variant="h6" fontWeight={600} gutterBottom>
              Change Password
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Update your password to keep your account secure
            </Typography>
          </Box>
          <Card sx={{ maxWidth: 600 }}>
            <Box sx={{ p: 3 }}>
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  if (changePasswordForm.new_password !== changePasswordForm.confirm_password) {
                    toast.error('New passwords do not match')
                    return
                  }
                  changePasswordMutation.mutate({
                    current_password: changePasswordForm.current_password,
                    new_password: changePasswordForm.new_password,
                  })
                }}
              >
                <Stack spacing={3}>
                  <TextField
                    label="Current Password"
                    type="password"
                    value={changePasswordForm.current_password}
                    onChange={(e) =>
                      setChangePasswordForm({
                        ...changePasswordForm,
                        current_password: e.target.value,
                      })
                    }
                    required
                    fullWidth
                  />

                  <TextField
                    label="New Password"
                    type="password"
                    value={changePasswordForm.new_password}
                    onChange={(e) =>
                      setChangePasswordForm({ ...changePasswordForm, new_password: e.target.value })
                    }
                    required
                    fullWidth
                  />

                  <TextField
                    label="Confirm New Password"
                    type="password"
                    value={changePasswordForm.confirm_password}
                    onChange={(e) =>
                      setChangePasswordForm({
                        ...changePasswordForm,
                        confirm_password: e.target.value,
                      })
                    }
                    required
                    fullWidth
                    error={
                      changePasswordForm.confirm_password !== '' &&
                      changePasswordForm.new_password !== changePasswordForm.confirm_password
                    }
                    helperText={
                      changePasswordForm.confirm_password !== '' &&
                      changePasswordForm.new_password !== changePasswordForm.confirm_password
                        ? 'Passwords do not match'
                        : ''
                    }
                  />

                  <Box>
                    <Button
                      type="submit"
                      variant="contained"
                      disabled={changePasswordMutation.isPending}
                      startIcon={
                        changePasswordMutation.isPending ? <CircularProgress size={16} /> : null
                      }
                    >
                      {changePasswordMutation.isPending
                        ? 'Changing Password...'
                        : 'Change Password'}
                    </Button>
                  </Box>
                </Stack>
              </form>
            </Box>
          </Card>
        </Box>
      )}

      {/* Appearance Tab */}
      {activeTab === 1 && (
        <Box>
          <Box>
            <Typography variant="h6" fontWeight={600} gutterBottom>
              Appearance
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Customize the look and feel of the application
            </Typography>
          </Box>
          <Card sx={{ maxWidth: 600 }}>
            <Box sx={{ p: 3 }}>
              <Stack spacing={3}>
                <Box
                  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    {mode === 'dark' ? <Moon size={24} /> : <Sun size={24} />}
                    <Box>
                      <Typography variant="subtitle1" fontWeight={500}>
                        Theme
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Choose a theme
                      </Typography>
                    </Box>
                  </Box>
                  <FormControl sx={{ minWidth: 120 }} size="small">
                    <Select
                      value={mode}
                      onChange={(e) => setTheme(e.target.value as any)}
                      displayEmpty
                      inputProps={{ 'aria-label': 'Theme mode' }}
                    >
                      {availableThemes.map((themeOption) => (
                        <MenuItem key={themeOption.id} value={themeOption.id}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            {themeOption.icon === 'Sun' ? <Sun size={16} /> : <Moon size={16} />}
                            {themeOption.label}
                          </Box>
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Box>
              </Stack>
            </Box>
          </Card>
        </Box>
      )}

      {/* Notifications Tab */}
      {activeTab === 2 && <NotificationsTab />}

      {/* System Packages Tab - Admin Only */}
      {activeTab === 3 && user?.is_admin && <PackagesTab />}

      {/* Scripts Tab */}
      {activeTab === (user?.is_admin ? 4 : 3) && <Scripts />}

      {/* Export/Import Tab */}
      {activeTab === (user?.is_admin ? 5 : 4) && <ExportImportTab />}

      {/* User Management Tab - Admin Only */}
      {activeTab === 6 && user?.is_admin && (
        <Box>
          <Box
            sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}
          >
            <Typography variant="h6" fontWeight={600}>
              User Management
            </Typography>
            <Button variant="contained" startIcon={<Plus size={18} />} onClick={openCreateUser}>
              Add User
            </Button>
          </Box>

          <DataTable
            data={usersData?.data?.users || []}
            columns={userColumns}
            actions={userActions}
            getRowKey={(user) => user.id}
            loading={loadingUsers}
            emptyState={{
              icon: <Users size={48} />,
              title: 'No users found',
              description: 'Create your first user to get started',
            }}
            variant="outlined"
          />
        </Box>
      )}

      {/* Activity Tab */}
      {activeTab === (user?.is_admin ? 7 : 5) && <Activity />}

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
        <DialogTitle>{editingUser ? 'Edit User' : 'Create User'}</DialogTitle>
        <form onSubmit={editingUser ? handleUpdateUser : handleCreateUser}>
          <DialogContent>
            <Stack spacing={3}>
              <TextField
                label="Username"
                value={userForm.username}
                onChange={(e) => setUserForm({ ...userForm, username: e.target.value })}
                required
                fullWidth
              />

              <TextField
                label="Email"
                type="email"
                value={userForm.email}
                onChange={(e) => setUserForm({ ...userForm, email: e.target.value })}
                required
                fullWidth
              />

              {!editingUser && (
                <TextField
                  label="Password"
                  type="password"
                  value={userForm.password}
                  onChange={(e) => setUserForm({ ...userForm, password: e.target.value })}
                  required
                  fullWidth
                />
              )}

              <FormControlLabel
                control={
                  <Checkbox
                    checked={userForm.is_admin}
                    onChange={(e) => setUserForm({ ...userForm, is_admin: e.target.checked })}
                  />
                }
                label="Admin User"
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button
              onClick={() => {
                setShowCreateUser(false)
                setEditingUser(null)
              }}
            >
              Cancel
            </Button>
            <Button type="submit" variant="contained">
              {editingUser ? 'Update' : 'Create'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Password Reset Modal */}
      <Dialog
        open={showPasswordModal}
        onClose={() => {
          setShowPasswordModal(false)
          setSelectedUserId(null)
        }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Reset Password</DialogTitle>
        <form onSubmit={handleResetPassword}>
          <DialogContent>
            <TextField
              label="New Password"
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
                setShowPasswordModal(false)
                setSelectedUserId(null)
              }}
            >
              Cancel
            </Button>
            <Button type="submit" variant="contained">
              Reset Password
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
              Delete User
            </Typography>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Are you sure you want to delete the user{' '}
            <strong>"{deleteConfirmUser?.username}"</strong>?
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            This action cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteConfirmUser(null)}>Cancel</Button>
          <Button
            onClick={handleDeleteUser}
            variant="contained"
            color="error"
            disabled={deleteUserMutation.isPending}
            startIcon={deleteUserMutation.isPending ? <CircularProgress size={16} /> : null}
          >
            {deleteUserMutation.isPending ? 'Deleting...' : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default Settings
