import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation } from '@tanstack/react-query'
import { Box, Card, Stack } from '@mui/material'
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
import AccountSecuritySection from './AccountSecuritySection'
import AccountAccessSection from './AccountAccessSection'
import AccountPasswordDialog from './AccountPasswordDialog'
import AccountTabNavigation, { AccountView } from './AccountTabNavigation'

const AccountTab: React.FC = () => {
  const { t } = useTranslation()
  const { user, hasGlobalPermission, refreshUser } = useAuth()
  const { trackSettings, EventAction } = useAnalytics()
  const canManageSystem = hasGlobalPermission('settings.system.manage')
  const hasGlobalRepositoryAccess = hasGlobalPermission('repositories.manage_all')

  const [accountView, setAccountView] = useState<AccountView>('profile')
  const [showChangePasswordDialog, setShowChangePasswordDialog] = useState(false)
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
      toast.success('Personal profile updated')
      await refreshUser()
      trackSettings(EventAction.EDIT, { section: 'account', operation: 'update_personal_profile' })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(translateBackendKey(error.response?.data?.detail) || 'Failed to update profile')
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
      toast.success('Deployment profile updated')
      await refreshUser()
      trackSettings(EventAction.EDIT, {
        section: 'account',
        operation: 'update_deployment_profile',
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || 'Failed to update deployment profile'
      )
    },
  })

  useEffect(() => {
    if (!user) return
    setProfileForm({
      username: user.username || '',
      email: user.email || '',
      full_name: user.full_name || '',
    })
    setDeploymentForm({
      deployment_type: user.deployment_type === 'enterprise' ? 'enterprise' : 'individual',
      enterprise_name: user.enterprise_name || '',
    })
  }, [user?.username, user?.email, user?.full_name, user?.deployment_type, user?.enterprise_name])

  useEffect(() => {
    if (user?.must_change_password) {
      setShowChangePasswordDialog(true)
      setAccountView('security')
    }
  }, [user?.must_change_password])

  const setAccountSurface = (view: AccountView) => {
    setAccountView(view)
    trackSettings(EventAction.VIEW, { section: 'account', surface: view })
  }

  const accountDisplayName = user?.full_name || user?.username || ''
  const deploymentLabel =
    user?.deployment_type === 'enterprise'
      ? user.enterprise_name || 'Enterprise deployment'
      : 'Individual deployment'
  const currentUserRolePresentation = getGlobalRolePresentation(user?.role, t)

  return (
    <>
      <Stack spacing={3}>
        {user && (
          <AccountTabHeader
            username={user.username}
            displayName={accountDisplayName}
            subtitle={
              user?.deployment_type === 'enterprise'
                ? 'Your personal profile is separate from the system-wide deployment identity.'
                : 'Your personal account settings, security, and access are managed here.'
            }
            roleLabel={currentUserRolePresentation.label}
            roleColor={currentUserRolePresentation.color}
            createdAt={user.created_at}
            deploymentLabel={deploymentLabel}
          />
        )}

        <Card variant="outlined" sx={{ borderRadius: 3, overflow: 'hidden' }}>
          <AccountTabNavigation value={accountView} onChange={setAccountSurface} />
          <Box sx={{ p: { xs: 2, md: 2.5 } }}>
            {accountView === 'profile' && (
              <AccountProfileSection
                canManageSystem={canManageSystem}
                showSetupBanner={!!user?.must_change_password}
                profileForm={profileForm}
                deploymentForm={deploymentForm}
                isSavingProfile={updateProfileMutation.isPending}
                isSavingDeployment={updateDeploymentMutation.isPending}
                onProfileFormChange={(updates) =>
                  setProfileForm((current) => ({ ...current, ...updates }))
                }
                onDeploymentFormChange={(updates) =>
                  setDeploymentForm((current) => ({ ...current, ...updates }))
                }
                onSaveProfile={() => updateProfileMutation.mutate(profileForm)}
                onSaveDeployment={() => updateDeploymentMutation.mutate(deploymentForm)}
              />
            )}

            {accountView === 'security' && (
              <AccountSecuritySection
                mustChangePassword={!!user?.must_change_password}
                onOpenChangePassword={() => {
                  setShowChangePasswordDialog(true)
                  trackSettings(EventAction.VIEW, {
                    section: 'account',
                    operation: 'open_change_password_dialog',
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
    </>
  )
}

export default AccountTab
