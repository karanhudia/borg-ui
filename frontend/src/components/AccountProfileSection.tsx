import { Box, Button, CircularProgress, Stack, TextField, Typography } from '@mui/material'
import { User, Building2, Pencil, ShieldCheck, KeyRound, Calendar, Fingerprint } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import AccountSecuritySection from './AccountSecuritySection'
import { formatDateShort } from '../utils/dateUtils'

export interface AccountProfileFormData {
  username: string
  email: string
  full_name: string
}

export interface DeploymentProfileFormData {
  deployment_type: 'individual' | 'enterprise'
  enterprise_name: string
}

interface AccountProfileSectionProps {
  canManageSystem: boolean
  profileForm: AccountProfileFormData
  deploymentForm: DeploymentProfileFormData
  isSavingProfile: boolean
  isSavingDeployment: boolean
  onProfileFormChange: (updates: Partial<AccountProfileFormData>) => void
  onDeploymentFormChange: (updates: Partial<DeploymentProfileFormData>) => void
  onSaveProfile: () => void
  onSaveDeployment: () => void
  onOpenChangePassword: () => void
  onOpenEditProfile: () => void
  roleLabel: string
  isAdmin: boolean
  isOperator: boolean
  createdAt: string
  totpEnabled: boolean
  passkeyCount: number
}

export default function AccountProfileSection({
  canManageSystem,
  profileForm,
  deploymentForm,
  isSavingDeployment,
  onDeploymentFormChange,
  onSaveDeployment,
  onOpenChangePassword,
  onOpenEditProfile,
  roleLabel,
  isAdmin,
  isOperator,
  createdAt,
  totpEnabled,
  passkeyCount,
}: AccountProfileSectionProps) {
  const { t } = useTranslation()

  // Badge color schemes
  const roleBadge = isAdmin
    ? {
        bg: 'rgba(168,85,247,0.12)',
        border: 'rgba(168,85,247,0.28)',
        text: 'rgb(192,132,252)',
        icon: ShieldCheck,
      }
    : isOperator
      ? {
          bg: 'rgba(14,165,233,0.12)',
          border: 'rgba(14,165,233,0.28)',
          text: 'rgb(56,189,248)',
          icon: KeyRound,
        }
      : {
          bg: 'rgba(255,255,255,0.06)',
          border: 'rgba(255,255,255,0.12)',
          text: 'rgb(161,161,170)',
          icon: User,
        }

  const RoleIcon = roleBadge.icon

  return (
    <Stack spacing={3.5}>
      {/* ── Info banner ── */}
      <Box
        sx={{
          px: { xs: 2, md: 3 },
          py: { xs: 2.25, md: 2.75 },
          borderRadius: 3,
          border: '1px solid',
          borderColor: 'rgba(14,165,233,0.18)',
          background:
            'linear-gradient(135deg, rgba(2,132,199,0.12) 0%, rgba(8,47,73,0.06) 55%, rgba(255,255,255,0.02) 100%)',
        }}
      >
        <Stack spacing={2.5}>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            justifyContent="space-between"
            alignItems={{ xs: 'flex-start', sm: 'center' }}
            gap={1.5}
          >
            <Stack direction="row" spacing={1.25} alignItems="center">
              <Box
                sx={{
                  width: 34,
                  height: 34,
                  borderRadius: 1.75,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  bgcolor: 'rgba(14,165,233,0.14)',
                  border: '1px solid rgba(14,165,233,0.24)',
                }}
              >
                <User size={16} />
              </Box>
              <Box>
                <Typography
                  variant="caption"
                  sx={{
                    display: 'block',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    color: 'info.light',
                    mb: 0.35,
                  }}
                >
                  {t('settings.account.profile.title')}
                </Typography>
                <Typography variant="h6" fontWeight={700} sx={{ lineHeight: 1.1 }}>
                  {profileForm.full_name || profileForm.username}
                </Typography>
              </Box>
            </Stack>

            {/* ── Role & status badges ── */}
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
              {/* Role badge */}
              <Box
                sx={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 0.6,
                  px: 1.25,
                  py: 0.5,
                  borderRadius: 10,
                  bgcolor: roleBadge.bg,
                  border: '1px solid',
                  borderColor: roleBadge.border,
                }}
              >
                <RoleIcon size={12} style={{ color: roleBadge.text }} />
                <Typography
                  variant="caption"
                  sx={{
                    fontWeight: 700,
                    color: roleBadge.text,
                    lineHeight: 1,
                    letterSpacing: '0.02em',
                  }}
                >
                  {roleLabel}
                </Typography>
              </Box>

              {/* TOTP badge */}
              {totpEnabled && (
                <Box
                  sx={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 0.6,
                    px: 1.25,
                    py: 0.5,
                    borderRadius: 10,
                    bgcolor: 'rgba(34,197,94,0.10)',
                    border: '1px solid rgba(34,197,94,0.24)',
                  }}
                >
                  <ShieldCheck size={12} style={{ color: 'rgb(74,222,128)' }} />
                  <Typography
                    variant="caption"
                    sx={{
                      fontWeight: 700,
                      color: 'rgb(74,222,128)',
                      lineHeight: 1,
                      letterSpacing: '0.02em',
                    }}
                  >
                    {t('settings.account.profile.badges.totpActive')}
                  </Typography>
                </Box>
              )}

              {/* Passkey badge */}
              {passkeyCount > 0 && (
                <Box
                  sx={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 0.6,
                    px: 1.25,
                    py: 0.5,
                    borderRadius: 10,
                    bgcolor: 'rgba(251,191,36,0.10)',
                    border: '1px solid rgba(251,191,36,0.24)',
                  }}
                >
                  <Fingerprint size={12} style={{ color: 'rgb(252,211,77)' }} />
                  <Typography
                    variant="caption"
                    sx={{
                      fontWeight: 700,
                      color: 'rgb(252,211,77)',
                      lineHeight: 1,
                      letterSpacing: '0.02em',
                    }}
                  >
                    {t('settings.account.profile.badges.passkeyActive', { count: passkeyCount })}
                  </Typography>
                </Box>
              )}

              {/* Member since badge */}
              {createdAt && (
                <Box
                  sx={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 0.6,
                    px: 1.25,
                    py: 0.5,
                    borderRadius: 10,
                    bgcolor: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(255,255,255,0.10)',
                  }}
                >
                  <Calendar size={12} style={{ color: 'rgb(161,161,170)', opacity: 0.8 }} />
                  <Typography
                    variant="caption"
                    sx={{
                      fontWeight: 600,
                      color: 'text.secondary',
                      lineHeight: 1,
                      letterSpacing: '0.02em',
                    }}
                  >
                    {t('settings.account.profile.badges.memberSince', {
                      date: formatDateShort(createdAt),
                    })}
                  </Typography>
                </Box>
              )}
            </Stack>
          </Stack>

          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ maxWidth: 720, fontSize: { md: '0.95rem' } }}
          >
            {t('settings.account.profile.description')}
          </Typography>

          {/* Highlights */}
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', md: 'repeat(3, minmax(0, 1fr))' },
              gap: 1.5,
            }}
          >
            {[
              {
                label: t('settings.users.fields.username'),
                value: profileForm.username || '—',
              },
              {
                label: t('settings.users.fields.email'),
                value: profileForm.email || '—',
              },
              {
                label: t('settings.users.fields.fullName'),
                value: profileForm.full_name || '—',
              },
            ].map((item) => (
              <Box
                key={item.label}
                sx={{
                  p: 1.75,
                  borderRadius: 2.5,
                  border: '1px solid rgba(255,255,255,0.08)',
                  bgcolor: 'rgba(255,255,255,0.04)',
                }}
              >
                <Typography
                  variant="caption"
                  sx={{
                    display: 'block',
                    mb: 0.75,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    color: 'text.secondary',
                  }}
                >
                  {item.label}
                </Typography>
                <Typography variant="subtitle2" fontWeight={700} noWrap>
                  {item.value}
                </Typography>
              </Box>
            ))}
          </Box>
        </Stack>
      </Box>

      {/* ── Two-column grid: Edit Profile card + Password card ── */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', xl: 'repeat(2, minmax(0, 1fr))' },
          gap: 3,
          alignItems: 'start',
        }}
      >
        {/* Edit profile — clickable card */}
        <Box>
          <Typography variant="subtitle2" fontWeight={700} gutterBottom>
            {t('settings.account.profile.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t('settings.account.profile.description')}
          </Typography>
          <Box
            onClick={onOpenEditProfile}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onOpenEditProfile()
              }
            }}
            role="button"
            tabIndex={0}
            aria-label={t('settings.account.editProfile')}
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
              borderColor: 'rgba(255,255,255,0.07)',
              background:
                'linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)',
              transition: 'border-color 180ms ease, background 180ms ease',
              '&:hover': {
                borderColor: 'rgba(255,255,255,0.14)',
                background:
                  'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.03) 100%)',
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
                  background:
                    'linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.03) 100%)',
                  border: '1px solid rgba(255,255,255,0.08)',
                }}
              >
                <Pencil size={16} style={{ opacity: 0.45 }} />
              </Box>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="body2" fontWeight={600} noWrap>
                  {t('settings.account.editProfile')}
                </Typography>
                <Typography variant="caption" color="text.secondary" noWrap>
                  {profileForm.username} · {profileForm.email}
                </Typography>
              </Box>
            </Stack>
            <Box
              sx={{
                fontSize: '0.75rem',
                fontWeight: 600,
                color: 'text.secondary',
                flexShrink: 0,
                opacity: 0.7,
              }}
            >
              →
            </Box>
          </Box>
        </Box>

        {/* Password section */}
        <Box>
          <Typography variant="subtitle2" fontWeight={700} gutterBottom>
            {t('settings.account.security.accountPassword')}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t('settings.account.security.changeCredentialsHint')}
          </Typography>
          <AccountSecuritySection onOpenChangePassword={onOpenChangePassword} />
        </Box>
      </Box>

      {/* ── Deployment profile (admin only) ── */}
      {canManageSystem && (
        <Box>
          <Typography variant="subtitle2" fontWeight={700} gutterBottom>
            {t('settings.account.profile.deployment.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t('settings.account.profile.deployment.description')}
          </Typography>

          <Box
            sx={{
              p: 2.5,
              borderRadius: 2.5,
              border: '1px solid',
              borderColor: 'divider',
              background:
                'linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)',
            }}
          >
            <Stack spacing={2.5}>
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' },
                  gap: 1.5,
                }}
              >
                {(
                  [
                    {
                      key: 'individual',
                      title: t('settings.account.profile.deployment.individual'),
                      body: t('settings.account.profile.deployment.individualDesc'),
                      icon: <User size={16} />,
                    },
                    {
                      key: 'enterprise',
                      title: t('settings.account.profile.deployment.enterprise'),
                      body: t('settings.account.profile.deployment.enterpriseDesc'),
                      icon: <Building2 size={16} />,
                    },
                  ] as const
                ).map((option) => {
                  const isSelected = deploymentForm.deployment_type === option.key
                  return (
                    <Box
                      key={option.key}
                      onClick={() => onDeploymentFormChange({ deployment_type: option.key })}
                      sx={{
                        p: 2,
                        border: '1px solid',
                        borderColor: isSelected
                          ? 'rgba(14,165,233,0.35)'
                          : 'rgba(255,255,255,0.07)',
                        borderRadius: 2.5,
                        cursor: 'pointer',
                        background: isSelected
                          ? 'linear-gradient(135deg, rgba(2,132,199,0.1) 0%, rgba(8,47,73,0.05) 100%)'
                          : 'linear-gradient(135deg, rgba(255,255,255,0.02) 0%, rgba(255,255,255,0.005) 100%)',
                        transition: 'border-color 180ms ease, background 180ms ease',
                        '&:hover': {
                          borderColor: isSelected
                            ? 'rgba(14,165,233,0.5)'
                            : 'rgba(255,255,255,0.14)',
                        },
                      }}
                    >
                      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 1 }}>
                        <Box
                          sx={{
                            width: 30,
                            height: 30,
                            borderRadius: 1.5,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            bgcolor: isSelected
                              ? 'rgba(14,165,233,0.14)'
                              : 'rgba(255,255,255,0.04)',
                            border: '1px solid',
                            borderColor: isSelected
                              ? 'rgba(14,165,233,0.24)'
                              : 'rgba(255,255,255,0.08)',
                          }}
                        >
                          {option.icon}
                        </Box>
                        <Typography variant="subtitle2" fontWeight={700}>
                          {option.title}
                        </Typography>
                      </Stack>
                      <Typography variant="body2" color="text.secondary" sx={{ pl: '42px' }}>
                        {option.body}
                      </Typography>
                    </Box>
                  )
                })}
              </Box>

              {deploymentForm.deployment_type === 'enterprise' && (
                <TextField
                  label={t('settings.account.profile.deployment.orgName')}
                  value={deploymentForm.enterprise_name}
                  onChange={(e) => onDeploymentFormChange({ enterprise_name: e.target.value })}
                  fullWidth
                  size="small"
                />
              )}

              <Box>
                <Button
                  variant="contained"
                  disabled={
                    isSavingDeployment ||
                    (deploymentForm.deployment_type === 'enterprise' &&
                      !deploymentForm.enterprise_name.trim())
                  }
                  startIcon={isSavingDeployment ? <CircularProgress size={14} /> : null}
                  onClick={onSaveDeployment}
                >
                  {isSavingDeployment
                    ? t('settings.account.profile.saving')
                    : t('settings.account.profile.deployment.saveButton')}
                </Button>
              </Box>
            </Stack>
          </Box>
        </Box>
      )}
    </Stack>
  )
}
