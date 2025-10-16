import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from 'react-query'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  TextField,
  CircularProgress,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
  Chip,
  FormControlLabel,
  Checkbox,
  Alert,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
} from '@mui/material'
import {
  Settings as SettingsIcon,
  Users,
  User,
  Shield,
  Save,
  Trash2,
  Plus,
  Edit,
  Key,
  RefreshCw,
  Server,
  AlertCircle,
} from 'lucide-react'
import { settingsAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { useAuth } from '../hooks/useAuth'

interface SystemSettings {
  backup_timeout: number
  max_concurrent_backups: number
  log_retention_days: number
  email_notifications: boolean
  webhook_url: string
  auto_cleanup: boolean
  cleanup_retention_days: number
  borg_version: string
  app_version: string
}

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
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState(0)
  const [showCreateUser, setShowCreateUser] = useState(false)
  const [editingUser, setEditingUser] = useState<UserType | null>(null)
  const [showPasswordModal, setShowPasswordModal] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [deleteConfirmUser, setDeleteConfirmUser] = useState<UserType | null>(null)

  // System settings
  const { data: systemSettings, isLoading: loadingSettings } = useQuery({
    queryKey: ['systemSettings'],
    queryFn: settingsAPI.getSystemSettings,
  })

  const updateSystemSettingsMutation = useMutation({
    mutationFn: settingsAPI.updateSystemSettings,
    onSuccess: () => {
      toast.success('System settings updated successfully')
      queryClient.invalidateQueries({ queryKey: ['systemSettings'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update system settings')
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

  // System cleanup
  const cleanupMutation = useMutation({
    mutationFn: settingsAPI.cleanupSystem,
    onSuccess: () => {
      toast.success('System cleanup completed')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to run system cleanup')
    },
  })

  // Form states
  const [systemForm, setSystemForm] = useState<Partial<SystemSettings>>({})
  const [userForm, setUserForm] = useState({
    username: '',
    email: '',
    password: '',
    is_admin: false,
  })
  const [passwordForm, setPasswordForm] = useState({
    new_password: '',
  })

  // Initialize form when data loads
  React.useEffect(() => {
    if (systemSettings?.data?.settings) {
      setSystemForm(systemSettings.data.settings)
    }
  }, [systemSettings])

  const handleSystemSettingsSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    updateSystemSettingsMutation.mutate(systemForm)
  }

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

  const handleCleanup = () => {
    cleanupMutation.mutate()
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

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" fontWeight={600} gutterBottom>
          Settings
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Manage system configuration and users
        </Typography>
      </Box>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={activeTab} onChange={(_, value) => setActiveTab(value)}>
          <Tab
            icon={<SettingsIcon size={18} />}
            iconPosition="start"
            label="System Settings"
            sx={{ textTransform: 'none', minHeight: 48 }}
          />
          {user?.is_admin && (
            <Tab
              icon={<Users size={18} />}
              iconPosition="start"
              label="User Management"
              sx={{ textTransform: 'none', minHeight: 48 }}
            />
          )}
          <Tab
            icon={<User size={18} />}
            iconPosition="start"
            label="Profile"
            sx={{ textTransform: 'none', minHeight: 48 }}
          />
        </Tabs>
      </Box>

      {/* System Settings Tab */}
      {activeTab === 0 && (
        <Box>
          {loadingSettings ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
              <CircularProgress size={48} />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                Loading system settings...
              </Typography>
            </Box>
          ) : (
            <Stack direction={{ xs: 'column', lg: 'row' }} spacing={3}>
              {/* System Settings Form */}
              <Box sx={{ flex: 1 }}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" fontWeight={600} gutterBottom>
                      System Configuration
                    </Typography>
                    <form onSubmit={handleSystemSettingsSubmit}>
                      <Stack spacing={3} sx={{ mt: 2 }}>
                        <TextField
                          label="Backup Timeout (seconds)"
                          type="number"
                          value={systemForm.backup_timeout || ''}
                          onChange={(e) =>
                            setSystemForm({ ...systemForm, backup_timeout: Number(e.target.value) })
                          }
                          inputProps={{ min: 300, max: 86400 }}
                          fullWidth
                        />

                        <TextField
                          label="Max Concurrent Backups"
                          type="number"
                          value={systemForm.max_concurrent_backups || ''}
                          onChange={(e) =>
                            setSystemForm({
                              ...systemForm,
                              max_concurrent_backups: Number(e.target.value),
                            })
                          }
                          inputProps={{ min: 1, max: 10 }}
                          fullWidth
                        />

                        <TextField
                          label="Log Retention (days)"
                          type="number"
                          value={systemForm.log_retention_days || ''}
                          onChange={(e) =>
                            setSystemForm({
                              ...systemForm,
                              log_retention_days: Number(e.target.value),
                            })
                          }
                          inputProps={{ min: 1, max: 365 }}
                          fullWidth
                        />

                        <TextField
                          label="Cleanup Retention (days)"
                          type="number"
                          value={systemForm.cleanup_retention_days || ''}
                          onChange={(e) =>
                            setSystemForm({
                              ...systemForm,
                              cleanup_retention_days: Number(e.target.value),
                            })
                          }
                          inputProps={{ min: 1, max: 365 }}
                          fullWidth
                        />

                        <FormControlLabel
                          control={
                            <Checkbox
                              checked={systemForm.email_notifications || false}
                              onChange={(e) =>
                                setSystemForm({
                                  ...systemForm,
                                  email_notifications: e.target.checked,
                                })
                              }
                            />
                          }
                          label="Enable Email Notifications"
                        />

                        <FormControlLabel
                          control={
                            <Checkbox
                              checked={systemForm.auto_cleanup || false}
                              onChange={(e) =>
                                setSystemForm({ ...systemForm, auto_cleanup: e.target.checked })
                              }
                            />
                          }
                          label="Enable Auto Cleanup"
                        />

                        <TextField
                          label="Webhook URL"
                          type="url"
                          value={systemForm.webhook_url || ''}
                          onChange={(e) =>
                            setSystemForm({ ...systemForm, webhook_url: e.target.value })
                          }
                          placeholder="https://example.com/webhook"
                          fullWidth
                        />

                        <Button
                          type="submit"
                          variant="contained"
                          startIcon={<Save size={18} />}
                          disabled={updateSystemSettingsMutation.isLoading}
                          fullWidth
                        >
                          {updateSystemSettingsMutation.isLoading ? 'Saving...' : 'Save Settings'}
                        </Button>
                      </Stack>
                    </form>
                  </CardContent>
                </Card>
              </Box>

              {/* System Information & Maintenance */}
              <Box sx={{ flex: 1 }}>
                <Stack spacing={3}>
                  {/* System Information */}
                  <Card>
                    <CardContent>
                      <Typography variant="h6" fontWeight={600} gutterBottom>
                        System Information
                      </Typography>
                      <List>
                        <ListItem>
                          <ListItemIcon>
                            <Server size={20} />
                          </ListItemIcon>
                          <ListItemText
                            primary="App Version"
                            secondary={systemForm.app_version}
                            primaryTypographyProps={{ variant: 'body2' }}
                            secondaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
                          />
                        </ListItem>
                        <ListItem>
                          <ListItemIcon>
                            <Shield size={20} />
                          </ListItemIcon>
                          <ListItemText
                            primary="Borg Version"
                            secondary={systemForm.borg_version}
                            primaryTypographyProps={{ variant: 'body2' }}
                            secondaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
                          />
                        </ListItem>
                      </List>
                    </CardContent>
                  </Card>

                  {/* System Maintenance */}
                  <Card>
                    <CardContent>
                      <Typography variant="h6" fontWeight={600} gutterBottom>
                        System Maintenance
                      </Typography>
                      <Button
                        variant="contained"
                        color="warning"
                        startIcon={<RefreshCw size={18} />}
                        onClick={handleCleanup}
                        disabled={cleanupMutation.isLoading}
                        fullWidth
                        sx={{ mt: 2 }}
                      >
                        {cleanupMutation.isLoading ? 'Running...' : 'Run System Cleanup'}
                      </Button>
                      <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                        Cleans up old logs, temporary files, and expired backups
                      </Typography>
                    </CardContent>
                  </Card>
                </Stack>
              </Box>
            </Stack>
          )}
        </Box>
      )}

      {/* User Management Tab */}
      {activeTab === 1 && user?.is_admin && (
        <Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <Typography variant="h6" fontWeight={600}>
              User Management
            </Typography>
            <Button
              variant="contained"
              startIcon={<Plus size={18} />}
              onClick={openCreateUser}
            >
              Add User
            </Button>
          </Box>

          {loadingUsers ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
              <CircularProgress size={48} />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                Loading users...
              </Typography>
            </Box>
          ) : (
            <Card>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>User</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Role</TableCell>
                      <TableCell>Created</TableCell>
                      <TableCell>Last Login</TableCell>
                      <TableCell align="right">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {usersData?.data?.users?.map((user: UserType) => (
                      <TableRow key={user.id}>
                        <TableCell>
                          <Box>
                            <Typography variant="body2" fontWeight={500}>
                              {user.username}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {user.email}
                            </Typography>
                          </Box>
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={user.is_active ? 'Active' : 'Inactive'}
                            color={user.is_active ? 'success' : 'error'}
                            size="small"
                          />
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={user.is_admin ? 'Admin' : 'User'}
                            color={user.is_admin ? 'secondary' : 'default'}
                            size="small"
                          />
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2">
                            {new Date(user.created_at).toLocaleDateString()}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" color="text.secondary">
                            {user.last_login
                              ? new Date(user.last_login).toLocaleDateString()
                              : 'Never'}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                            <IconButton size="small" onClick={() => openEditUser(user)} color="primary">
                              <Edit size={16} />
                            </IconButton>
                            <IconButton
                              size="small"
                              onClick={() => openPasswordModal(user.id)}
                              color="warning"
                            >
                              <Key size={16} />
                            </IconButton>
                            <IconButton
                              size="small"
                              onClick={() => setDeleteConfirmUser(user)}
                              color="error"
                            >
                              <Trash2 size={16} />
                            </IconButton>
                          </Stack>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Card>
          )}
        </Box>
      )}

      {/* Profile Tab */}
      {activeTab === 2 && (
        <Card>
          <CardContent>
            <Typography variant="h6" fontWeight={600} gutterBottom>
              Profile Settings
            </Typography>
            <Alert severity="info" sx={{ mt: 2 }}>
              Profile management coming soon...
            </Alert>
          </CardContent>
        </Card>
      )}

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
            disabled={deleteUserMutation.isLoading}
            startIcon={deleteUserMutation.isLoading ? <CircularProgress size={16} /> : null}
          >
            {deleteUserMutation.isLoading ? 'Deleting...' : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default Settings
