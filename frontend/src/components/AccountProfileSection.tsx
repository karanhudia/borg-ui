import {
  Box,
  Button,
  CircularProgress,
  Stack,
  TextField,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
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
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  // Theme-aware surface tokens
  const subtleBorder = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.09)'
  const subtleBg = isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)'
  const cardBorder = isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.09)'
  const cardBorderHover = isDark ? 'rgba(255,255,255,0.14)' : 'rgba(0,0,0,0.16)'
  const cardGradient = isDark
    ? 'linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)'
    : 'linear-gradient(135deg, rgba(0,0,0,0.015) 0%, rgba(0,0,0,0.005) 100%)'
  const cardHoverGradient = isDark
    ? 'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.03) 100%)'
    : 'linear-gradient(135deg, rgba(0,0,0,0.03) 0%, rgba(0,0,0,0.015) 100%)'
  const iconBoxGradient = isDark
    ? 'linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.03) 100%)'
    : 'linear-gradient(135deg, rgba(0,0,0,0.04) 0%, rgba(0,0,0,0.02) 100%)'
  const iconBoxBorder = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)'

  // Badge color schemes
  // Badge text takes the theme's palette shades, which clear 4.5:1 on their
  // own tint in both modes. The 400-level hues these used were dark-only.
  const tintBadge = (color: string) => ({
    bg: alpha(color, 0.12),
    border: alpha(color, 0.28),
    text: color,
  })
  const roleBadge = isAdmin
    ? { ...tintBadge(theme.palette.secondary.main), icon: ShieldCheck }
    : isOperator
      ? { ...tintBadge(theme.palette.info.main), icon: KeyRound }
      : {
          bg: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)',
          border: isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.12)',
          text: theme.palette.text.secondary,
          icon: User,
        }
  const totpBadge = tintBadge(theme.palette.success.main)
  const passkeyBadge = tintBadge(theme.palette.warning.main)

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
            sx={{
              justifyContent: 'space-between',
              alignItems: { xs: 'flex-start', sm: 'center' },
              gap: 1.5,
            }}
          >
            <Stack
              direction="row"
              spacing={1.25}
              sx={{
                alignItems: 'center',
              }}
            >
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
                    color: 'info.main',
                    mb: 0.35,
                  }}
                >
                  {t('settings.account.profile.title')}
                </Typography>
                <Typography
                  variant="h6"
                  sx={{
                    fontWeight: 700,
                    lineHeight: 1.1,
                  }}
                >
                  {profileForm.full_name || profileForm.username}
                </Typography>
              </Box>
            </Stack>

            {/* ── Role & status badges ── */}
            <Stack
              direction="row"
              spacing={0.75}
              useFlexGap
              sx={{
                flexWrap: 'wrap',
              }}
            >
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
                    bgcolor: totpBadge.bg,
                    border: `1px solid ${totpBadge.border}`,
                  }}
                >
                  <ShieldCheck size={12} style={{ color: totpBadge.text }} />
                  <Typography
                    variant="caption"
                    sx={{
                      fontWeight: 700,
                      color: totpBadge.text,
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
                    bgcolor: passkeyBadge.bg,
                    border: `1px solid ${passkeyBadge.border}`,
                  }}
                >
                  <Fingerprint size={12} style={{ color: passkeyBadge.text }} />
                  <Typography
                    variant="caption"
                    sx={{
                      fontWeight: 700,
                      color: passkeyBadge.text,
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
                    bgcolor: subtleBg,
                    border: '1px solid',
                    borderColor: subtleBorder,
                  }}
                >
                  <Calendar size={12} style={{ color: theme.palette.text.secondary }} />
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
            sx={{
              color: 'text.secondary',
              maxWidth: 720,
              fontSize: { md: '0.95rem' },
            }}
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
                  border: '1px solid',
                  borderColor: subtleBorder,
                  bgcolor: subtleBg,
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
                <Typography
                  variant="subtitle2"
                  noWrap
                  sx={{
                    fontWeight: 700,
                  }}
                >
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
              borderColor: cardBorder,
              background: cardGradient,
              transition: 'border-color 180ms ease, background 180ms ease',
              '&:hover': {
                borderColor: cardBorderHover,
                background: cardHoverGradient,
              },
            }}
          >
            <Stack
              direction="row"
              spacing={2}
              sx={{
                alignItems: 'center',
                minWidth: 0,
              }}
            >
              <Box
                sx={{
                  width: 38,
                  height: 38,
                  borderRadius: 1.5,
                  flexShrink: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: iconBoxGradient,
                  border: '1px solid',
                  borderColor: iconBoxBorder,
                }}
              >
                <Pencil size={16} style={{ opacity: 0.45 }} />
              </Box>
              <Box sx={{ minWidth: 0 }}>
                <Typography
                  variant="body2"
                  noWrap
                  sx={{
                    fontWeight: 600,
                  }}
                >
                  {t('settings.account.editProfile')}
                </Typography>
                <Typography
                  variant="caption"
                  noWrap
                  sx={{
                    color: 'text.secondary',
                  }}
                >
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
              }}
            >
              →
            </Box>
          </Box>
        </Box>

        {/* Password section */}
        <Box>
          <AccountSecuritySection onOpenChangePassword={onOpenChangePassword} />
        </Box>
      </Box>

      {/* ── Deployment profile (admin only) ── */}
      {canManageSystem && (
        <Box>
          <Typography
            variant="subtitle2"
            gutterBottom
            sx={{
              fontWeight: 700,
            }}
          >
            {t('settings.account.profile.deployment.title')}
          </Typography>
          <Typography
            variant="body2"
            sx={{
              color: 'text.secondary',
              mb: 2,
            }}
          >
            {t('settings.account.profile.deployment.description')}
          </Typography>

          <Box
            sx={{
              p: 2.5,
              borderRadius: 2.5,
              border: '1px solid',
              borderColor: 'divider',
              background: cardGradient,
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
                        borderColor: isSelected ? 'rgba(14,165,233,0.35)' : cardBorder,
                        borderRadius: 2.5,
                        cursor: 'pointer',
                        background: isSelected
                          ? 'linear-gradient(135deg, rgba(2,132,199,0.1) 0%, rgba(8,47,73,0.05) 100%)'
                          : cardGradient,
                        transition: 'border-color 180ms ease, background 180ms ease',
                        '&:hover': {
                          borderColor: isSelected ? 'rgba(14,165,233,0.5)' : cardBorderHover,
                        },
                      }}
                    >
                      <Stack
                        direction="row"
                        spacing={1.5}
                        sx={{
                          alignItems: 'center',
                          mb: 1,
                        }}
                      >
                        <Box
                          sx={{
                            width: 30,
                            height: 30,
                            borderRadius: 1.5,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            bgcolor: isSelected ? 'rgba(14,165,233,0.14)' : subtleBg,
                            border: '1px solid',
                            borderColor: isSelected ? 'rgba(14,165,233,0.24)' : subtleBorder,
                          }}
                        >
                          {option.icon}
                        </Box>
                        <Typography
                          variant="subtitle2"
                          sx={{
                            fontWeight: 700,
                          }}
                        >
                          {option.title}
                        </Typography>
                      </Stack>
                      <Typography
                        variant="body2"
                        sx={{
                          color: 'text.secondary',
                          pl: '42px',
                        }}
                      >
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
