import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery } from '@tanstack/react-query'
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
import { authAPI, settingsAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import QRCode from 'qrcode'
import { useAuth } from '../hooks/useAuth'
import { useAnalytics } from '../hooks/useAnalytics'
import { getApiErrorDetail } from '../utils/apiErrors'
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
import { createPasskeyCredential } from '../utils/webauthn'
import { getDefaultPasskeyDeviceName } from '../utils/passkeyDeviceName'
import AccountSecuritySettingsSection from './AccountSecuritySettingsSection'
import ResponsiveDialog from './ResponsiveDialog'

const AccountTab: React.FC = () => {
  const { t } = useTranslation()
  const {
    user,
    hasGlobalPermission,
    refreshUser,
    proxyAuthEnabled,
    markRecentPasswordConfirmation,
  } = useAuth()
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
  const [showTotpSetupDialog, setShowTotpSetupDialog] = useState(false)
  const [showTotpDisableDialog, setShowTotpDisableDialog] = useState(false)
  const [totpSetupPassword, setTotpSetupPassword] = useState('')
  const [totpSetupToken, setTotpSetupToken] = useState<string | null>(null)
  const [totpSecret, setTotpSecret] = useState('')
  const [totpOtpAuthUri, setTotpOtpAuthUri] = useState('')
  const [totpQrCodeDataUrl, setTotpQrCodeDataUrl] = useState('')
  const [totpRecoveryCodes, setTotpRecoveryCodes] = useState<string[]>([])
  const [totpVerificationCode, setTotpVerificationCode] = useState('')
  const [totpDisablePassword, setTotpDisablePassword] = useState('')
  const [totpDisableCode, setTotpDisableCode] = useState('')
  const [showPasskeyDialog, setShowPasskeyDialog] = useState(false)
  const [passkeyPassword, setPasskeyPassword] = useState('')
  const { data: totpStatus, refetch: refetchTotpStatus } = useQuery({
    queryKey: ['auth', 'totp-status'],
    queryFn: async () => {
      const response = await authAPI.getTotpStatus()
      return response.data
    },
    enabled: !!user && !proxyAuthEnabled,
  })

  const { data: passkeys = [], refetch: refetchPasskeys } = useQuery({
    queryKey: ['auth', 'passkeys'],
    queryFn: async () => {
      const response = await authAPI.listPasskeys()
      return response.data
    },
    enabled: !!user && !proxyAuthEnabled,
  })

  const changePasswordMutation = useMutation({
    mutationFn: (passwordData: { current_password: string; new_password: string }) =>
      settingsAPI.changePassword(passwordData),
    onSuccess: async () => {
      toast.success(t('settings.toasts.passwordChanged'))
      markRecentPasswordConfirmation(changePasswordForm.new_password)
      setChangePasswordForm({ current_password: '', new_password: '', confirm_password: '' })
      setShowChangePasswordDialog(false)
      await refreshUser()
      trackSettings(EventAction.EDIT, { section: 'account', operation: 'change_password' })
    },
    onError: (error: unknown) => {
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) || t('settings.toasts.failedToChangePassword')
      )
    },
  })

  const beginTotpSetupMutation = useMutation({
    mutationFn: (currentPassword: string) => authAPI.beginTotpSetup(currentPassword),
    onSuccess: ({ data }) => {
      setTotpSetupToken(data.setup_token)
      setTotpSecret(data.secret)
      setTotpOtpAuthUri(data.otpauth_uri)
      setTotpRecoveryCodes(data.recovery_codes)
      toast.success(t('settings.account.security.totpSetupStarted'))
    },
    onError: (error: unknown) => {
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) ||
          t('settings.account.security.totpSetupFailed')
      )
    },
  })

  const enableTotpMutation = useMutation({
    mutationFn: () => {
      if (!totpSetupToken) {
        throw new Error('Missing setup token')
      }
      return authAPI.enableTotp(totpSetupToken, totpVerificationCode)
    },
    onSuccess: async ({ data }) => {
      toast.success(t('settings.account.security.totpEnabledToast'))
      setTotpRecoveryCodes(data.recovery_codes)
      await refreshUser()
      await refetchTotpStatus()
    },
    onError: (error: unknown) => {
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) ||
          t('settings.account.security.totpEnableFailed')
      )
    },
  })

  const disableTotpMutation = useMutation({
    mutationFn: () => authAPI.disableTotp(totpDisablePassword, totpDisableCode),
    onSuccess: async () => {
      toast.success(t('settings.account.security.totpDisabledToast'))
      setShowTotpDisableDialog(false)
      setTotpDisablePassword('')
      setTotpDisableCode('')
      setTotpRecoveryCodes([])
      await refreshUser()
      await refetchTotpStatus()
    },
    onError: (error: unknown) => {
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) ||
          t('settings.account.security.totpDisableFailed')
      )
    },
  })

  const addPasskeyMutation = useMutation({
    mutationFn: async () => {
      const beginResponse = await authAPI.beginPasskeyRegistration(passkeyPassword)
      const credential = await createPasskeyCredential(beginResponse.data.options)
      return authAPI.finishPasskeyRegistration(
        beginResponse.data.ceremony_token,
        credential,
        getDefaultPasskeyDeviceName()
      )
    },
    onSuccess: async () => {
      toast.success(t('settings.account.security.passkeyAddedToast'))
      setShowPasskeyDialog(false)
      setPasskeyPassword('')
      await refreshUser()
      await refetchPasskeys()
      trackSettings(EventAction.CREATE, {
        section: 'account',
        operation: 'add_passkey',
        surface: 'security',
      })
    },
    onError: (error: unknown) => {
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) ||
          t('settings.account.security.passkeyAddFailed')
      )
    },
  })

  const deletePasskeyMutation = useMutation({
    mutationFn: (passkeyId: number) => authAPI.deletePasskey(passkeyId),
    onSuccess: async () => {
      toast.success(t('settings.account.security.passkeyDeletedToast'))
      await refreshUser()
      await refetchPasskeys()
      trackSettings(EventAction.DELETE, {
        section: 'account',
        operation: 'delete_passkey',
        surface: 'security',
      })
    },
    onError: (error: unknown) => {
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) ||
          t('settings.account.security.passkeyDeleteFailed')
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
  const showSecurityTab = !proxyAuthEnabled

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

  useEffect(() => {
    let cancelled = false

    if (!totpOtpAuthUri) {
      setTotpQrCodeDataUrl('')
      return
    }

    QRCode.toDataURL(totpOtpAuthUri, {
      width: 220,
      margin: 1,
      errorCorrectionLevel: 'M',
    })
      .then((dataUrl: string) => {
        if (!cancelled) {
          setTotpQrCodeDataUrl(dataUrl)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTotpQrCodeDataUrl('')
        }
      })

    return () => {
      cancelled = true
    }
  }, [totpOtpAuthUri])

  useEffect(() => {
    if (!showSecurityTab && accountView === 'security') {
      setAccountView('profile')
    }
  }, [accountView, showSecurityTab])

  const closeTotpSetupDialog = () => {
    setShowTotpSetupDialog(false)
    setTotpSetupPassword('')
    setTotpSetupToken(null)
    setTotpSecret('')
    setTotpOtpAuthUri('')
    setTotpQrCodeDataUrl('')
    setTotpVerificationCode('')
    setTotpRecoveryCodes([])
  }

  return (
    <>
      <Stack spacing={3}>
        <AccountTabHeader />

        <Card variant="outlined" sx={{ borderRadius: 3, overflow: 'hidden' }}>
          <AccountTabNavigation
            value={accountView}
            onChange={setAccountSurface}
            showSecurityTab={showSecurityTab}
          />
          <Box sx={{ p: { xs: 2, md: 2.5 } }}>
            {accountView === 'profile' && (
              <AccountProfileSection
                canManageSystem={canManageSystem}
                profileForm={profileForm}
                deploymentForm={deploymentForm}
                isSavingProfile={updateProfileMutation.isPending}
                isSavingDeployment={updateDeploymentMutation.isPending}
                roleLabel={currentUserRolePresentation.label}
                isAdmin={currentUserRolePresentation.isAdminRole}
                isOperator={currentUserRolePresentation.isOperatorRole}
                createdAt={user?.created_at || ''}
                totpEnabled={!!user?.totp_enabled}
                passkeyCount={user?.passkey_count ?? 0}
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

            {accountView === 'security' && showSecurityTab && (
              <AccountSecuritySettingsSection
                totpEnabled={!!user?.totp_enabled}
                recoveryCodesRemaining={totpStatus?.recovery_codes_remaining ?? 0}
                totpLoading={
                  beginTotpSetupMutation.isPending ||
                  enableTotpMutation.isPending ||
                  disableTotpMutation.isPending
                }
                onEnableTotp={() => setShowTotpSetupDialog(true)}
                onDisableTotp={() => setShowTotpDisableDialog(true)}
                passkeys={passkeys}
                passkeysLoading={addPasskeyMutation.isPending || deletePasskeyMutation.isPending}
                onAddPasskey={() => setShowPasskeyDialog(true)}
                onDeletePasskey={(passkeyId) => deletePasskeyMutation.mutate(passkeyId)}
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
        currentPassword={changePasswordForm.current_password}
        newPassword={changePasswordForm.new_password}
        confirmPassword={changePasswordForm.confirm_password}
        isSubmitting={changePasswordMutation.isPending}
        onClose={() => setShowChangePasswordDialog(false)}
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

      <ResponsiveDialog
        open={showTotpSetupDialog}
        onClose={closeTotpSetupDialog}
        fullWidth
        maxWidth="sm"
        footer={
          <DialogActions sx={{ px: { xs: 2, sm: 3 }, py: 1.5 }}>
            <Button onClick={closeTotpSetupDialog}>{t('common.buttons.cancel')}</Button>
            {!totpSetupToken ? (
              <Button
                variant="contained"
                disabled={!totpSetupPassword || beginTotpSetupMutation.isPending}
                onClick={() => beginTotpSetupMutation.mutate(totpSetupPassword)}
              >
                {t('common.buttons.next')}
              </Button>
            ) : (
              <Button
                variant="contained"
                disabled={!totpVerificationCode || enableTotpMutation.isPending}
                onClick={() =>
                  enableTotpMutation.mutate(undefined, {
                    onSuccess: () => {
                      setShowTotpSetupDialog(false)
                      setTotpSetupPassword('')
                      setTotpSetupToken(null)
                      setTotpSecret('')
                      setTotpOtpAuthUri('')
                      setTotpQrCodeDataUrl('')
                      setTotpVerificationCode('')
                    },
                  })
                }
              >
                {t('settings.account.security.enableTotp')}
              </Button>
            )}
          </DialogActions>
        }
      >
        <DialogTitle>{t('settings.account.security.enableTotp')}</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: 1 }}>
          {!totpSetupToken ? (
            <>
              <Typography variant="body2" color="text.secondary">
                {t('settings.account.security.totpSetupIntro')}
              </Typography>
              <TextField
                label={t('settings.account.security.currentPasswordLabel')}
                type="password"
                value={totpSetupPassword}
                onChange={(event) => setTotpSetupPassword(event.target.value)}
                fullWidth
                size="small"
              />
            </>
          ) : (
            <>
              <Typography variant="body2" color="text.secondary">
                {t('settings.account.security.totpSetupInstructions')}
              </Typography>
              {totpQrCodeDataUrl ? (
                <Box
                  sx={{
                    p: 2,
                    borderRadius: 2,
                    bgcolor: 'action.hover',
                    display: 'grid',
                    justifyItems: 'center',
                    gap: 1.25,
                  }}
                >
                  <Box
                    component="img"
                    src={totpQrCodeDataUrl}
                    alt={t('settings.account.security.totpQrCodeAlt')}
                    sx={{
                      width: 220,
                      maxWidth: '100%',
                      borderRadius: 1.5,
                      bgcolor: '#fff',
                      p: 1,
                    }}
                  />
                  <Typography variant="caption" color="text.secondary" align="center">
                    {t('settings.account.security.totpQrCodeHint')}
                  </Typography>
                </Box>
              ) : null}
              <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: 'action.hover' }}>
                <Typography variant="caption" color="text.secondary">
                  {t('settings.account.security.manualSecret')}
                </Typography>
                <Typography
                  variant="body2"
                  sx={{ mt: 0.5, fontFamily: 'monospace', fontWeight: 700, wordBreak: 'break-all' }}
                >
                  {totpSecret}
                </Typography>
              </Box>
              <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: 'action.hover' }}>
                <Typography variant="caption" color="text.secondary">
                  {t('settings.account.security.recoveryCodesTitle')}
                </Typography>
                <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mt: 1 }}>
                  {totpRecoveryCodes.map((code) => (
                    <Typography
                      key={code}
                      variant="body2"
                      sx={{
                        px: 1,
                        py: 0.5,
                        borderRadius: 1,
                        bgcolor: 'background.paper',
                        fontFamily: 'monospace',
                      }}
                    >
                      {code}
                    </Typography>
                  ))}
                </Stack>
              </Box>
              <TextField
                label={t('settings.account.security.totpVerificationLabel')}
                value={totpVerificationCode}
                onChange={(event) => setTotpVerificationCode(event.target.value)}
                fullWidth
                size="small"
              />
            </>
          )}
        </DialogContent>
      </ResponsiveDialog>

      <ResponsiveDialog
        open={showTotpDisableDialog}
        onClose={() => setShowTotpDisableDialog(false)}
        fullWidth
        maxWidth="sm"
        footer={
          <DialogActions sx={{ px: { xs: 2, sm: 3 }, py: 1.5 }}>
            <Button onClick={() => setShowTotpDisableDialog(false)}>
              {t('common.buttons.cancel')}
            </Button>
            <Button
              variant="contained"
              color="error"
              disabled={!totpDisablePassword || !totpDisableCode || disableTotpMutation.isPending}
              onClick={() => disableTotpMutation.mutate()}
            >
              {t('settings.account.security.disableTotp')}
            </Button>
          </DialogActions>
        }
      >
        <DialogTitle>{t('settings.account.security.disableTotp')}</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {t('settings.account.security.totpDisableIntro')}
          </Typography>
          <TextField
            label={t('settings.account.security.currentPasswordLabel')}
            type="password"
            value={totpDisablePassword}
            onChange={(event) => setTotpDisablePassword(event.target.value)}
            fullWidth
            size="small"
          />
          <TextField
            label={t('settings.account.security.totpVerificationLabel')}
            value={totpDisableCode}
            onChange={(event) => setTotpDisableCode(event.target.value)}
            fullWidth
            size="small"
            helperText={t('settings.account.security.totpDisableHint')}
          />
        </DialogContent>
      </ResponsiveDialog>

      <ResponsiveDialog
        open={showPasskeyDialog}
        onClose={() => setShowPasskeyDialog(false)}
        fullWidth
        maxWidth="sm"
        footer={
          <DialogActions sx={{ px: { xs: 2, sm: 3 }, py: 1.5 }}>
            <Button onClick={() => setShowPasskeyDialog(false)}>
              {t('common.buttons.cancel')}
            </Button>
            <Button
              variant="contained"
              disabled={!passkeyPassword || addPasskeyMutation.isPending}
              onClick={() => addPasskeyMutation.mutate()}
            >
              {t('settings.account.security.addPasskey')}
            </Button>
          </DialogActions>
        }
      >
        <DialogTitle>{t('settings.account.security.addPasskey')}</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {t('settings.account.security.passkeySetupIntro')}
          </Typography>
          <TextField
            label={t('settings.account.security.currentPasswordLabel')}
            type="password"
            value={passkeyPassword}
            onChange={(event) => setPasskeyPassword(event.target.value)}
            fullWidth
            size="small"
          />
        </DialogContent>
      </ResponsiveDialog>
    </>
  )
}

export default AccountTab
