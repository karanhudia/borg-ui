import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation } from '@tanstack/react-query'
import {
  Box,
  Button,
  Card,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { settingsAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { useAuth } from '../hooks/useAuth'
import { useAnalytics } from '../hooks/useAnalytics'
import { getGlobalRolePresentation } from '../utils/rolePresentation'
import { translateBackendKey } from '../utils/translateBackendKey'
import AccountTabHeader from './AccountTabHeader'
import AccountProfileSection, {
  AccountProfileFormData,
  DeploymentProfileFormData,
} from './AccountProfileSection'
import AccountAccessSection from './AccountAccessSection'
import AccountPasswordDialog from './AccountPasswordDialog'
import AccountTabNavigation, { AccountView } from './AccountTabNavigation'
import { clearPasswordSetupPromptSeen } from '../utils/passwordSetupPrompt'
import ResponsiveDialog from './ResponsiveDialog'

const AccountTab: React.FC = () => {
  const { t } = useTranslation()
  const { user, hasGlobalPermission, refreshUser } = useAuth()
  const { trackSettings, EventAction } = useAnalytics()
  const canManageSystem = hasGlobalPermission('settings.system.manage')
  const hasGlobalRepositoryAccess = hasGlobalPermission('repositories.manage_all')

  const [accountView, setAccountView] = useState<AccountView>('profile')
  const [showChangePasswordDialog, setShowChangePasswordDialog] = useState(false)
  const [showEditProfileDialog, setShowEditProfileDialog] = useState(false)
  const [changePasswordForm, setChangePasswordForm] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  })
  const [profileForm, setProfileForm] = useState<AccountProfileFormData>({
    username: '',
    email: '',
    full_name: '',
  })
  const [deploymentForm, setDeploymentForm] = useState<DeploymentProfileFormData>({
    deployment_type: 'individual' as 'individual' | 'enterprise',
    enterprise_name: '',
  })

  const changePasswordMutation = useMutation({
    mutationFn: (passwordData: { current_password: string; new_password: string }) =>
      settingsAPI.changePassword(passwordData),
    onSuccess: async () => {
      toast.success(t('settings.toasts.passwordChanged'))
      setChangePasswordForm({ current_password: '', new_password: '', confirm_password: '' })
      setShowChangePasswordDialog(false)
      if (user?.username) {
        clearPasswordSetupPromptSeen(user.username)
      }
      await refreshUser()
      trackSettings(EventAction.EDIT, { section: 'account', operation: 'change_password' })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('settings.toasts.failedToChangePassword')
      )
    },
  })

  const updateProfileMutation = useMutation({
    mutationFn: async (data: AccountProfileFormData) => {
      await settingsAPI.updateProfile({
        username: data.username,
        email: data.email,
        full_name: data.full_name,
      })
    },
    onSuccess: async () => {
      toast.success(t('settings.account.toasts.profileUpdated'))
      await refreshUser()
      trackSettings(EventAction.EDIT, { section: 'account', operation: 'update_personal_profile' })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('settings.account.toasts.failedToUpdateProfile')
      )
    },
  })

  const updateDeploymentMutation = useMutation({
    mutationFn: async (data: DeploymentProfileFormData) => {
      await settingsAPI.updateSystemSettings({
        deployment_type: data.deployment_type,
        enterprise_name: data.deployment_type === 'enterprise' ? data.enterprise_name : null,
      } as Parameters<typeof settingsAPI.updateSystemSettings>[0])
    },
    onSuccess: async () => {
      toast.success(t('settings.account.toasts.deploymentUpdated'))
      await refreshUser()
      trackSettings(EventAction.EDIT, {
        section: 'account',
        operation: 'update_deployment_profile',
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('settings.account.toasts.failedToUpdateDeployment')
      )
    },
  })

  const setAccountSurface = (view: AccountView) => {
    setAccountView(view)
    trackSettings(EventAction.VIEW, { section: 'account', surface: view })
  }

  const username = user?.username || ''
  const email = user?.email || ''
  const fullName = user?.full_name || ''
  const userId = user?.id
  const deploymentType = user?.deployment_type === 'enterprise' ? 'enterprise' : 'individual'
  const enterpriseName = user?.enterprise_name || ''

  const currentUserRolePresentation = getGlobalRolePresentation(user?.role, t)

  useEffect(() => {
    if (!userId) return
    setProfileForm({
      username,
      email,
      full_name: fullName,
    })
    setDeploymentForm({
      deployment_type: deploymentType,
      enterprise_name: enterpriseName,
    })
  }, [deploymentType, email, enterpriseName, fullName, userId, username])

  return (
    <>
      <Stack spacing={3}>
        <AccountTabHeader />

        <Card variant="outlined" sx={{ borderRadius: 3, overflow: 'hidden' }}>
          <AccountTabNavigation value={accountView} onChange={setAccountSurface} />
          <Box sx={{ p: { xs: 2, md: 2.5 } }}>
            {accountView === 'profile' && (
              <AccountProfileSection
                canManageSystem={canManageSystem}
                mustChangePassword={!!user?.must_change_password}
                profileForm={profileForm}
                deploymentForm={deploymentForm}
                isSavingProfile={updateProfileMutation.isPending}
                isSavingDeployment={updateDeploymentMutation.isPending}
                roleLabel={currentUserRolePresentation.label}
                isAdmin={currentUserRolePresentation.isAdminRole}
                isOperator={currentUserRolePresentation.isOperatorRole}
                createdAt={user?.created_at || ''}
                onProfileFormChange={(updates) =>
                  setProfileForm((current) => ({ ...current, ...updates }))
                }
                onDeploymentFormChange={(updates) =>
                  setDeploymentForm((current) => ({ ...current, ...updates }))
                }
                onSaveProfile={() => updateProfileMutation.mutate(profileForm)}
                onSaveDeployment={() => updateDeploymentMutation.mutate(deploymentForm)}
                onOpenChangePassword={() => {
                  setShowChangePasswordDialog(true)
                  trackSettings(EventAction.VIEW, {
                    section: 'account',
                    operation: 'open_change_password_dialog',
                  })
                }}
                onOpenEditProfile={() => {
                  setShowEditProfileDialog(true)
                  trackSettings(EventAction.VIEW, {
                    section: 'account',
                    operation: 'open_edit_profile_dialog',
                  })
                }}
              />
            )}

            {accountView === 'access' && (
              <AccountAccessSection hasGlobalRepositoryAccess={hasGlobalRepositoryAccess} />
            )}
          </Box>
        </Card>
      </Stack>

      <AccountPasswordDialog
        open={showChangePasswordDialog}
        mustChangePassword={!!user?.must_change_password}
        currentPassword={changePasswordForm.current_password}
        newPassword={changePasswordForm.new_password}
        confirmPassword={changePasswordForm.confirm_password}
        isSubmitting={changePasswordMutation.isPending}
        onClose={(reason) => {
          if (
            user?.must_change_password &&
            (reason === 'backdropClick' || reason === 'escapeKeyDown')
          ) {
            return
          }
          setShowChangePasswordDialog(false)
        }}
        onFormChange={(updates) => setChangePasswordForm((current) => ({ ...current, ...updates }))}
        onSubmit={() => {
          if (changePasswordForm.new_password !== changePasswordForm.confirm_password) {
            toast.error(t('settings.toasts.passwordsDoNotMatch'))
            return
          }
          changePasswordMutation.mutate({
            current_password: changePasswordForm.current_password,
            new_password: changePasswordForm.new_password,
          })
        }}
      />

      <ResponsiveDialog
        open={showEditProfileDialog}
        onClose={() => setShowEditProfileDialog(false)}
        fullWidth
        maxWidth="sm"
        footer={
          <DialogActions sx={{ px: { xs: 2, sm: 3 }, py: 1.5 }}>
            <Button onClick={() => setShowEditProfileDialog(false)}>
              {t('common.buttons.cancel')}
            </Button>
            <Button
              variant="contained"
              disabled={updateProfileMutation.isPending}
              onClick={() =>
                updateProfileMutation.mutate(profileForm, {
                  onSuccess: () => setShowEditProfileDialog(false),
                })
              }
            >
              {updateProfileMutation.isPending
                ? t('settings.account.profile.saving')
                : t('settings.account.profile.saveButton')}
            </Button>
          </DialogActions>
        }
      >
        <DialogTitle>{t('settings.account.profile.title')}</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {t('settings.account.profile.description')}
          </Typography>
          <TextField
            label={t('settings.users.fields.username')}
            value={profileForm.username}
            onChange={(e) => setProfileForm((c) => ({ ...c, username: e.target.value }))}
            required
            fullWidth
            size="small"
          />
          <TextField
            label={t('settings.users.fields.email')}
            type="email"
            value={profileForm.email}
            onChange={(e) => setProfileForm((c) => ({ ...c, email: e.target.value }))}
            required
            fullWidth
            size="small"
          />
          <TextField
            label={t('settings.users.fields.fullName')}
            value={profileForm.full_name}
            onChange={(e) => setProfileForm((c) => ({ ...c, full_name: e.target.value }))}
            fullWidth
            size="small"
          />
        </DialogContent>
      </ResponsiveDialog>
    </>
  )
}

export default AccountTab
