import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation } from '@tanstack/react-query'
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
  Tabs,
  Tab,
} from '@mui/material'
import { User, Lock, ShieldCheck } from 'lucide-react'
import { settingsAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { useAuth } from '../hooks/useAuth'
import { useAnalytics } from '../hooks/useAnalytics'
import { translateBackendKey } from '../utils/translateBackendKey'
import { formatDateShort } from '../utils/dateUtils'
import ApiTokensSection from './ApiTokensSection'
import UserPermissionsPanel from './UserPermissionsPanel'

const AccountTab: React.FC = () => {
  const { t } = useTranslation()
  const { user, isAdmin, refreshUser } = useAuth()
  const { trackSettings, EventAction } = useAnalytics()

  const [accountView, setAccountView] = useState<'profile' | 'security' | 'access'>('profile')
  const [showChangePasswordDialog, setShowChangePasswordDialog] = useState(false)
  const [changePasswordForm, setChangePasswordForm] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  })
  const [profileForm, setProfileForm] = useState({
    username: '',
    email: '',
    full_name: '',
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
    mutationFn: async (data: typeof profileForm) => {
      await settingsAPI.updateProfile({
        username: data.username,
        email: data.email,
        full_name: data.full_name,
      })
      if (isAdmin) {
        await settingsAPI.updateSystemSettings({
          deployment_type: data.deployment_type,
          enterprise_name: data.deployment_type === 'enterprise' ? data.enterprise_name : null,
        } as Parameters<typeof settingsAPI.updateSystemSettings>[0])
      }
    },
    onSuccess: async () => {
      toast.success('Profile updated')
      await refreshUser()
      trackSettings(EventAction.EDIT, { section: 'account', operation: 'update_profile' })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(translateBackendKey(error.response?.data?.detail) || 'Failed to update profile')
    },
  })

  useEffect(() => {
    if (!user) return
    setProfileForm({
      username: user.username || '',
      email: user.email || '',
      full_name: user.full_name || '',
      deployment_type: user.deployment_type === 'enterprise' ? 'enterprise' : 'individual',
      enterprise_name: user.enterprise_name || '',
    })
  }, [user])

  useEffect(() => {
    if (user?.must_change_password) {
      setShowChangePasswordDialog(true)
      setAccountView('security')
    }
  }, [user?.must_change_password])

  const setAccountSurface = (view: 'profile' | 'security' | 'access') => {
    setAccountView(view)
    trackSettings(EventAction.VIEW, { section: 'account', surface: view })
  }

  const accountDisplayName =
    user?.deployment_type === 'enterprise'
      ? user.enterprise_name || user.full_name || user.username
      : user?.full_name || user?.username
  const currentUserRoleLabel = isAdmin
    ? t('settings.users.roles.admin')
    : user?.role === 'operator'
      ? t('settings.users.roles.operator')
      : t('settings.users.roles.viewer')

  return (
    <>
      <Stack spacing={3}>
        {user && (
          <Card variant="outlined" sx={{ borderRadius: 3, overflow: 'hidden' }}>
            <Box
              sx={{
                px: { xs: 2.5, md: 3.5 },
                py: { xs: 2.5, md: 3 },
                background:
                  'linear-gradient(180deg, rgba(23,23,23,0.03) 0%, rgba(23,23,23,0.00) 100%)',
                borderBottom: '1px solid',
                borderColor: 'divider',
              }}
            >
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={2}
                alignItems={{ xs: 'flex-start', sm: 'center' }}
                justifyContent="space-between"
              >
                <Stack direction="row" spacing={2} alignItems="center">
                  <Box
                    sx={{
                      width: 60,
                      height: 60,
                      borderRadius: 2,
                      bgcolor: '#171717',
                      color: '#fff',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '1.25rem',
                      fontWeight: 700,
                      flexShrink: 0,
                    }}
                  >
                    {user.username.charAt(0).toUpperCase()}
                  </Box>
                  <Box>
                    <Typography variant="h5" fontWeight={700}>
                      {accountDisplayName}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {user?.deployment_type === 'enterprise'
                        ? 'Enterprise deployment settings, security, and access are managed here.'
                        : 'Personal account settings, security, and access are managed here.'}
                    </Typography>
                  </Box>
                </Stack>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Chip
                    label={currentUserRoleLabel}
                    color={
                      user.role === 'admin'
                        ? 'secondary'
                        : user.role === 'operator'
                          ? 'info'
                          : 'default'
                    }
                    size="small"
                  />
                  <Chip label={`@${user.username}`} variant="outlined" size="small" />
                  <Chip
                    label={`Member since ${formatDateShort(user.created_at)}`}
                    variant="outlined"
                    size="small"
                  />
                </Stack>
              </Stack>
            </Box>
          </Card>
        )}

        <Card variant="outlined" sx={{ borderRadius: 3, overflow: 'hidden' }}>
          <Box sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
            <Tabs
              value={accountView === 'profile' ? 0 : accountView === 'security' ? 1 : 2}
              onChange={(_, v) =>
                setAccountSurface(v === 0 ? 'profile' : v === 1 ? 'security' : 'access')
              }
              sx={{ px: { xs: 1, md: 2 } }}
            >
              <Tab
                icon={<User size={15} />}
                iconPosition="start"
                label="Profile"
                sx={{ minHeight: 48, gap: 0.5, textTransform: 'none', fontWeight: 600 }}
              />
              <Tab
                icon={<Lock size={15} />}
                iconPosition="start"
                label="Security"
                sx={{ minHeight: 48, gap: 0.5, textTransform: 'none', fontWeight: 600 }}
              />
              <Tab
                icon={<ShieldCheck size={15} />}
                iconPosition="start"
                label="Access"
                sx={{ minHeight: 48, gap: 0.5, textTransform: 'none', fontWeight: 600 }}
              />
            </Tabs>
          </Box>
          <Box sx={{ p: { xs: 2, md: 2.5 } }}>
            {accountView === 'profile' && (
              <Stack spacing={3}>
                {user?.must_change_password && (
                  <Box
                    sx={{
                      px: 2,
                      py: 1.5,
                      border: '1px solid',
                      borderColor: 'warning.main',
                      borderRadius: 2.5,
                      bgcolor: 'warning.50',
                    }}
                  >
                    <Typography variant="body2" fontWeight={700}>
                      Finish account setup
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Change your password first, then optionally add your personal or enterprise
                      profile details below.
                    </Typography>
                  </Box>
                )}
                {isAdmin && (
                  <Box>
                    <Typography variant="subtitle1" fontWeight={700} gutterBottom>
                      Deployment profile
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      Choose how this deployment presents itself across the UI.
                    </Typography>
                    <Box
                      sx={{
                        display: 'grid',
                        gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' },
                        gap: 2,
                        mb: 2,
                      }}
                    >
                      {(
                        [
                          {
                            key: 'individual',
                            title: 'Individual',
                            body: 'Show admin full name as the account identity.',
                          },
                          {
                            key: 'enterprise',
                            title: 'Enterprise',
                            body: 'Show an organization name as the deployment identity.',
                          },
                        ] as const
                      ).map((option) => (
                        <Box
                          key={option.key}
                          onClick={() =>
                            setProfileForm({
                              ...profileForm,
                              deployment_type: option.key,
                              enterprise_name:
                                option.key === 'individual' ? '' : profileForm.enterprise_name,
                            })
                          }
                          sx={{
                            p: 2.5,
                            border: '1px solid',
                            borderColor:
                              profileForm.deployment_type === option.key
                                ? 'primary.main'
                                : 'divider',
                            borderRadius: 2.5,
                            cursor: 'pointer',
                            bgcolor:
                              profileForm.deployment_type === option.key
                                ? 'rgba(8,145,178,0.06)'
                                : 'background.paper',
                            transition: 'border-color 160ms ease, background-color 160ms ease',
                          }}
                        >
                          <Typography variant="subtitle2" fontWeight={700} gutterBottom>
                            {option.title}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {option.body}
                          </Typography>
                        </Box>
                      ))}
                    </Box>
                    {profileForm.deployment_type === 'enterprise' && (
                      <TextField
                        label="Organization name"
                        value={profileForm.enterprise_name}
                        onChange={(e) =>
                          setProfileForm({ ...profileForm, enterprise_name: e.target.value })
                        }
                        fullWidth
                        size="small"
                      />
                    )}
                  </Box>
                )}
                <form
                  onSubmit={(e) => {
                    e.preventDefault()
                    updateProfileMutation.mutate(profileForm)
                  }}
                >
                  <Stack spacing={2}>
                    <TextField
                      label={t('settings.users.fields.username')}
                      value={profileForm.username}
                      onChange={(e) => setProfileForm({ ...profileForm, username: e.target.value })}
                      required
                      fullWidth
                      size="small"
                    />
                    <TextField
                      label={t('settings.users.fields.email')}
                      type="email"
                      value={profileForm.email}
                      onChange={(e) => setProfileForm({ ...profileForm, email: e.target.value })}
                      required
                      fullWidth
                      size="small"
                    />
                    <TextField
                      label="Full name"
                      value={profileForm.full_name}
                      onChange={(e) =>
                        setProfileForm({ ...profileForm, full_name: e.target.value })
                      }
                      fullWidth
                      size="small"
                    />
                    {user?.role !== 'admin' &&
                      user?.deployment_type === 'enterprise' &&
                      user?.enterprise_name && (
                        <TextField
                          label="Organization"
                          value={user.enterprise_name}
                          fullWidth
                          size="small"
                          disabled
                          helperText="Managed by your admin"
                        />
                      )}
                    <Box>
                      <Button
                        type="submit"
                        variant="contained"
                        disabled={updateProfileMutation.isPending}
                        startIcon={
                          updateProfileMutation.isPending ? <CircularProgress size={14} /> : null
                        }
                      >
                        {updateProfileMutation.isPending ? 'Saving profile' : 'Save profile'}
                      </Button>
                    </Box>
                  </Stack>
                </form>
              </Stack>
            )}

            {accountView === 'security' && (
              <Box
                onClick={() => {
                  setShowChangePasswordDialog(true)
                  trackSettings(EventAction.VIEW, {
                    section: 'account',
                    operation: 'open_change_password_dialog',
                  })
                }}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 2,
                  px: 2.5,
                  py: 2,
                  borderRadius: 2.5,
                  cursor: 'pointer',
                  border: '1px solid',
                  borderColor: user?.must_change_password
                    ? 'rgba(245,158,11,0.35)'
                    : 'rgba(255,255,255,0.07)',
                  background: user?.must_change_password
                    ? 'linear-gradient(135deg, rgba(120,53,15,0.18) 0%, rgba(146,64,14,0.10) 100%)'
                    : 'linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)',
                  transition: 'border-color 180ms ease, background 180ms ease',
                  '&:hover': {
                    borderColor: user?.must_change_password
                      ? 'rgba(245,158,11,0.6)'
                      : 'rgba(255,255,255,0.14)',
                    background: user?.must_change_password
                      ? 'linear-gradient(135deg, rgba(120,53,15,0.26) 0%, rgba(146,64,14,0.16) 100%)'
                      : 'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.03) 100%)',
                  },
                }}
              >
                <Stack direction="row" spacing={2} alignItems="center" sx={{ minWidth: 0 }}>
                  <Box
                    sx={{
                      width: 38,
                      height: 38,
                      borderRadius: 1.5,
                      flexShrink: 0,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      background: user?.must_change_password
                        ? 'linear-gradient(135deg, #92400e 0%, #b45309 100%)'
                        : 'linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.03) 100%)',
                      border: '1px solid',
                      borderColor: user?.must_change_password
                        ? 'rgba(245,158,11,0.4)'
                        : 'rgba(255,255,255,0.08)',
                    }}
                  >
                    <Lock
                      size={16}
                      style={{
                        color: user?.must_change_password ? '#fde68a' : undefined,
                        opacity: user?.must_change_password ? 1 : 0.45,
                      }}
                    />
                  </Box>
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="body2" fontWeight={600} noWrap>
                      {user?.must_change_password ? 'Password update required' : 'Account password'}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" noWrap>
                      {user?.must_change_password
                        ? 'Action required — you must update before continuing.'
                        : 'Click to change your login credentials'}
                    </Typography>
                  </Box>
                </Stack>
                <Box
                  sx={{
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    color: user?.must_change_password ? '#fbbf24' : 'text.secondary',
                    flexShrink: 0,
                    opacity: 0.7,
                    letterSpacing: '0.02em',
                  }}
                >
                  {user?.must_change_password ? 'Update →' : '→'}
                </Box>
              </Box>
            )}

            {accountView === 'access' && (
              <Stack spacing={3}>
                <Box>
                  <Stack direction="row" spacing={1.25} alignItems="center" sx={{ mb: 1 }}>
                    <ShieldCheck size={16} style={{ opacity: 0.6 }} />
                    <Typography variant="subtitle1" fontWeight={700}>
                      Access
                    </Typography>
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    Tokens and repository access live under the same account umbrella.
                  </Typography>
                </Box>
                <ApiTokensSection />
                {user?.role !== 'admin' ? (
                  <UserPermissionsPanel
                    title="Repository permissions"
                    subtitle="Your current repository-level access."
                  />
                ) : (
                  <Box
                    sx={{
                      px: 2.5,
                      py: 2,
                      border: '1px solid',
                      borderColor: 'divider',
                      borderRadius: 2.5,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1.5,
                      bgcolor: 'action.hover',
                    }}
                  >
                    <ShieldCheck size={16} style={{ color: '#f87171', flexShrink: 0 }} />
                    <Box>
                      <Typography variant="body2" fontWeight={700}>
                        Global access
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Admin accounts inherit full access to all repositories and settings.
                      </Typography>
                    </Box>
                  </Box>
                )}
              </Stack>
            )}
          </Box>
        </Card>
      </Stack>

      <Dialog
        open={showChangePasswordDialog}
        onClose={(_, reason) => {
          if (
            user?.must_change_password &&
            (reason === 'backdropClick' || reason === 'escapeKeyDown')
          ) {
            return
          }
          setShowChangePasswordDialog(false)
        }}
        maxWidth="sm"
        fullWidth
        disableEscapeKeyDown={!!user?.must_change_password}
      >
        <DialogTitle>
          {user?.must_change_password ? 'Complete account setup' : t('settings.password.title')}
        </DialogTitle>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (changePasswordForm.new_password !== changePasswordForm.confirm_password) {
              toast.error(t('settings.toasts.passwordsDoNotMatch'))
              return
            }
            changePasswordMutation.mutate({
              current_password: changePasswordForm.current_password,
              new_password: changePasswordForm.new_password,
            })
          }}
        >
          <DialogContent>
            <Stack spacing={2}>
              {user?.must_change_password && (
                <Typography variant="body2" color="text.secondary">
                  Your password must be changed before you can navigate outside account settings.
                </Typography>
              )}
              <TextField
                label={t('settings.password.current')}
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
                size="small"
              />
              <TextField
                label={t('settings.password.new')}
                type="password"
                value={changePasswordForm.new_password}
                onChange={(e) =>
                  setChangePasswordForm({
                    ...changePasswordForm,
                    new_password: e.target.value,
                  })
                }
                required
                fullWidth
                size="small"
              />
              <TextField
                label={t('settings.password.confirm')}
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
                size="small"
                error={
                  changePasswordForm.confirm_password !== '' &&
                  changePasswordForm.new_password !== changePasswordForm.confirm_password
                }
                helperText={
                  changePasswordForm.confirm_password !== '' &&
                  changePasswordForm.new_password !== changePasswordForm.confirm_password
                    ? t('settings.password.noMatch')
                    : ''
                }
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            {!user?.must_change_password && (
              <Button onClick={() => setShowChangePasswordDialog(false)}>
                {t('settings.users.buttons.cancel')}
              </Button>
            )}
            <Button
              type="submit"
              variant="contained"
              disabled={changePasswordMutation.isPending}
              startIcon={changePasswordMutation.isPending ? <CircularProgress size={14} /> : null}
            >
              {changePasswordMutation.isPending
                ? t('settings.password.submitting')
                : t('settings.password.submit')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </>
  )
}

export default AccountTab
