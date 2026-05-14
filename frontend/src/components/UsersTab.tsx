import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Stack } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import { Search, Users } from 'lucide-react'
import { toast } from 'react-hot-toast'
import DataTable from './DataTable'
import { settingsAPI, repositoriesAPI } from '../services/api'
import { useAuth } from '../hooks/useAuth'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuthorization } from '../hooks/useAuthorization'
import { usePlan } from '../hooks/usePlan'
import { getGlobalRolePresentation } from '../utils/rolePresentation'
import { translateBackendKey } from '../utils/translateBackendKey'
import {
  DeleteUserDialog,
  PasswordResetDialog,
  RepositoryAccessDialog,
  UserFormDialog,
} from './users/UserDialogs'
import { PendingSsoAlert, UsersFilterToolbar, UsersHeader, UsersStats } from './users/UsersOverview'
import { PasswordFormState, RoleFilter, StatusFilter, UserFormState, UserType } from './users/types'
import { useUserTableActions, useUserTableColumns } from './users/useUserTableConfig'

const emptyUserForm: UserFormState = {
  username: '',
  email: '',
  password: '',
  role: 'viewer',
  full_name: '',
  auth_source: 'local',
  oidc_subject: '',
}

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

  const [showCreateUser, setShowCreateUser] = useState(false)
  const [editingUser, setEditingUser] = useState<UserType | null>(null)
  const [showUserPasswordModal, setShowUserPasswordModal] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [accessUser, setAccessUser] = useState<UserType | null>(null)
  const [deleteConfirmUser, setDeleteConfirmUser] = useState<UserType | null>(null)
  const [selectedAccessUserId, setSelectedAccessUserId] = useState<number | null>(null)

  const [userForm, setUserForm] = useState<UserFormState>(emptyUserForm)
  const [passwordForm, setPasswordForm] = useState<PasswordFormState>({ new_password: '' })
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

  const users = useMemo<UserType[]>(() => usersData?.data?.users ?? [], [usersData?.data?.users])
  const userOidcFieldsExposed = users.some(
    (user) => 'auth_source' in user || 'oidc_subject' in user
  )

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

  const closeUserForm = () => {
    setShowCreateUser(false)
    setEditingUser(null)
  }

  const closePasswordModal = () => {
    setShowUserPasswordModal(false)
    setSelectedUserId(null)
  }

  const openPasswordModal = useCallback((userId: number) => {
    setSelectedUserId(userId)
    setShowUserPasswordModal(true)
    setPasswordForm({ new_password: '' })
  }, [])

  const openEditUser = useCallback((userToEdit: UserType) => {
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
  }, [])

  const openCreateUser = () => {
    setShowCreateUser(true)
    setUserForm(emptyUserForm)
  }

  useEffect(() => {
    if (accessUser) setSelectedAccessUserId(accessUser.id)
  }, [accessUser])

  const totalUsers = users.length
  const activeUsers = users.filter((u) => u.is_active).length
  const pendingSsoUsers = users.filter((u) => !u.is_active && u.auth_source === 'oidc').length
  const adminUsers = users.filter((u) => getRolePresentation(u.role).isAdminRole).length
  const operatorUsers = users.filter((u) => getRolePresentation(u.role).isOperatorRole).length
  const viewerUsers = users.length - adminUsers - operatorUsers

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
        if (roleFilter === 'viewer' && (presentation.isAdminRole || presentation.isOperatorRole)) {
          return false
        }
      }
      if (statusFilter === 'active' && !user.is_active) return false
      if (statusFilter === 'inactive' && user.is_active) return false
      if (statusFilter === 'pending_sso' && (user.is_active || user.auth_source !== 'oidc')) {
        return false
      }
      return true
    })
  }, [users, searchQuery, roleFilter, statusFilter, getRolePresentation])

  const hasActiveFilters =
    searchQuery.trim() !== '' || roleFilter !== 'all' || statusFilter !== 'all'

  const columns = useUserTableColumns({ isDark, getRolePresentation })
  const handleApproveSsoUser = useCallback(
    (user: UserType) => approveUserMutation.mutate(user.id),
    [approveUserMutation]
  )
  const tableActions = useUserTableActions({
    canManageUsers,
    onApproveSsoUser: handleApproveSsoUser,
    onManageAccess: setAccessUser,
    onEditUser: openEditUser,
    onResetPassword: openPasswordModal,
    onDeleteUser: setDeleteConfirmUser,
  })

  return (
    <>
      <Stack spacing={3}>
        <UsersHeader canCreateUser={can('multi_user')} onCreateUser={openCreateUser} />

        <UsersStats
          totalUsers={totalUsers}
          activeUsers={activeUsers}
          pendingSsoUsers={pendingSsoUsers}
          adminUsers={adminUsers}
          operatorUsers={operatorUsers}
          viewerUsers={viewerUsers}
        />

        <PendingSsoAlert
          pendingSsoUsers={pendingSsoUsers}
          statusFilter={statusFilter}
          onSetStatusFilter={setStatusFilter}
        />

        <UsersFilterToolbar
          loadingUsers={loadingUsers}
          userCount={users.length}
          filteredUserCount={filteredUsers.length}
          totalUsers={totalUsers}
          searchQuery={searchQuery}
          roleFilter={roleFilter}
          statusFilter={statusFilter}
          hasActiveFilters={hasActiveFilters}
          onSearchQueryChange={setSearchQuery}
          onRoleFilterChange={setRoleFilter}
          onStatusFilterChange={setStatusFilter}
        />

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

      <RepositoryAccessDialog
        accessUser={accessUser}
        selectedAccessUserId={selectedAccessUserId}
        repositories={repositoriesData?.data?.repositories ?? []}
        getRolePresentation={getRolePresentation}
        roleHasGlobalPermission={roleHasGlobalPermission}
        onClose={() => setAccessUser(null)}
      />

      <UserFormDialog
        open={showCreateUser || !!editingUser}
        editingUser={editingUser}
        userForm={userForm}
        userOidcFieldsExposed={userOidcFieldsExposed}
        onUserFormChange={setUserForm}
        onClose={closeUserForm}
        onSubmit={editingUser ? handleUpdateUser : handleCreateUser}
      />

      <PasswordResetDialog
        open={showUserPasswordModal}
        passwordForm={passwordForm}
        onPasswordFormChange={setPasswordForm}
        onClose={closePasswordModal}
        onSubmit={handleResetPassword}
      />

      <DeleteUserDialog
        user={deleteConfirmUser}
        isDeleting={deleteUserMutation.isPending}
        onClose={() => setDeleteConfirmUser(null)}
        onDelete={handleDeleteUser}
      />
    </>
  )
}

export default UsersTab
