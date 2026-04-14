import { useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'react-hot-toast'
import { Box, Button, CircularProgress, Stack, Typography } from '@mui/material'
import { Fingerprint, ShieldCheck, Zap, KeyRound } from 'lucide-react'
import { getApiErrorDetail } from '../utils/apiErrors'
import { translateBackendKey } from '../utils/translateBackendKey'
import { useAuth } from '../hooks/useAuth'
import { useAnalytics } from '../hooks/useAnalytics'
import ResponsiveDialog from './ResponsiveDialog'

interface PasskeyEnrollmentPromptProps {
  open: boolean
  onSnooze: () => void
  onIgnore: () => void
  onSuccess: () => Promise<void> | void
}

const BORG_GREEN = '#00dd00'
const BORG_GREEN_RING = 'rgba(0, 221, 0, 0.14)'

const BENEFITS = [
  {
    icon: Zap,
    titleKey: 'settings.account.security.passkeyBenefitFastTitle',
    descKey: 'settings.account.security.passkeyBenefitFastDesc',
    color: '#fbbf24',
    bg: 'rgba(251, 191, 36, 0.08)',
    border: 'rgba(251, 191, 36, 0.2)',
  },
  {
    icon: ShieldCheck,
    titleKey: 'settings.account.security.passkeyBenefitSecureTitle',
    descKey: 'settings.account.security.passkeyBenefitSecureDesc',
    color: '#4ade80',
    bg: 'rgba(74, 222, 128, 0.08)',
    border: 'rgba(74, 222, 128, 0.2)',
  },
  {
    icon: KeyRound,
    titleKey: 'settings.account.security.passkeyBenefitNoPasswordTitle',
    descKey: 'settings.account.security.passkeyBenefitNoPasswordDesc',
    color: '#60a5fa',
    bg: 'rgba(96, 165, 250, 0.08)',
    border: 'rgba(96, 165, 250, 0.2)',
  },
] as const

export default function PasskeyEnrollmentPrompt({
  open,
  onSnooze,
  onIgnore,
  onSuccess,
}: PasskeyEnrollmentPromptProps) {
  const { t } = useTranslation()
  const { enrollPasskeyFromRecentLogin } = useAuth()
  const { trackAuth, EventAction } = useAnalytics()

  useEffect(() => {
    if (!open) return
    trackAuth(EventAction.VIEW, { surface: 'post_login_passkey_prompt' })
  }, [EventAction.VIEW, open, trackAuth])

  const addPasskeyMutation = useMutation({
    mutationFn: async () => enrollPasskeyFromRecentLogin(),
    onSuccess: async () => {
      trackAuth(EventAction.COMPLETE, {
        surface: 'post_login_passkey_prompt',
        operation: 'enroll_passkey',
      })
      toast.success(t('settings.account.security.passkeyAddedToast'))
      await onSuccess()
    },
    onError: (error: unknown) => {
      trackAuth(EventAction.FAIL, {
        surface: 'post_login_passkey_prompt',
        operation: 'enroll_passkey',
      })
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) ||
          t('settings.account.security.passkeyAddFailed')
      )
    },
  })

  const isPending = addPasskeyMutation.isPending

  const handleClose = () => {
    if (isPending) return
    trackAuth('Snooze', { surface: 'post_login_passkey_prompt' })
    onSnooze()
  }

  const handleIgnore = () => {
    if (isPending) return
    trackAuth('Ignore', { surface: 'post_login_passkey_prompt' })
    onIgnore()
  }

  const handleSubmit = () => {
    trackAuth(EventAction.START, {
      surface: 'post_login_passkey_prompt',
      operation: 'enroll_passkey',
    })
    void addPasskeyMutation.mutateAsync()
  }

  return (
    <ResponsiveDialog
      open={open}
      onClose={handleClose}
      maxWidth="xs"
      fullWidth
      PaperProps={{
        sx: {
          borderRadius: 4,
          overflow: 'hidden',
          width: { sm: 420 },
          border: '1px solid rgba(0, 221, 0, 0.08)',
          boxShadow: '0 24px 48px rgba(0,0,0,0.4)',
        },
      }}
    >
      {/* Hero section */}
      <Box
        sx={{
          pt: { xs: 3.5, sm: 4 },
          pb: 2.5,
          px: { xs: 2.5, sm: 3 },
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* Ambient background glow */}
        <Box
          aria-hidden="true"
          sx={{
            position: 'absolute',
            top: -40,
            left: '50%',
            transform: 'translateX(-50%)',
            width: 280,
            height: 200,
            borderRadius: '50%',
            background: `radial-gradient(ellipse at center, rgba(0,221,0,0.04) 0%, transparent 70%)`,
            pointerEvents: 'none',
          }}
        />

        {/* Fingerprint icon with animated rings */}
        <Box
          sx={{
            position: 'relative',
            mb: 2.5,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {/* Outer pulse ring */}
          <Box
            aria-hidden="true"
            sx={{
              position: 'absolute',
              width: 96,
              height: 96,
              borderRadius: '50%',
              border: `1px solid ${BORG_GREEN_RING}`,
              animation: 'passkeyPulseOuter 2.4s ease-in-out infinite',
              '@keyframes passkeyPulseOuter': {
                '0%, 100%': { transform: 'scale(1)', opacity: 0.6 },
                '50%': { transform: 'scale(1.15)', opacity: 0 },
              },
            }}
          />
          {/* Inner pulse ring */}
          <Box
            aria-hidden="true"
            sx={{
              position: 'absolute',
              width: 80,
              height: 80,
              borderRadius: '50%',
              border: `1px solid rgba(0, 221, 0, 0.25)`,
              animation: 'passkeyPulseInner 2.4s ease-in-out 0.4s infinite',
              '@keyframes passkeyPulseInner': {
                '0%, 100%': { transform: 'scale(1)', opacity: 0.8 },
                '50%': { transform: 'scale(1.1)', opacity: 0 },
              },
            }}
          />
          {/* Icon container */}
          <Box
            sx={{
              width: 64,
              height: 64,
              borderRadius: '50%',
              background: `radial-gradient(135deg, rgba(0,221,0,0.18) 0%, rgba(0,221,0,0.06) 100%)`,
              border: `1.5px solid rgba(0, 221, 0, 0.3)`,
              boxShadow: `0 0 24px rgba(0, 221, 0, 0.2), inset 0 1px 0 rgba(0,221,0,0.15)`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              position: 'relative',
              zIndex: 1,
            }}
          >
            <Fingerprint size={28} color={BORG_GREEN} strokeWidth={1.5} />
          </Box>
        </Box>

        {/* Title */}
        <Typography
          variant="h6"
          sx={{
            fontWeight: 700,
            fontSize: { xs: '1.125rem', sm: '1.1875rem' },
            letterSpacing: '-0.01em',
            color: 'text.primary',
            mb: 0.75,
            lineHeight: 1.3,
          }}
        >
          {t('settings.account.security.passkeyPromptTitle')}
        </Typography>

        {/* Subtitle */}
        <Typography
          variant="body2"
          sx={{
            color: 'text.secondary',
            lineHeight: 1.6,
            maxWidth: 300,
            fontSize: '0.875rem',
          }}
        >
          {t('settings.account.security.passkeyPromptDescription')}
        </Typography>
      </Box>

      {/* Benefits */}
      <Stack
        spacing={1}
        sx={{
          px: { xs: 2.5, sm: 3 },
          pb: 2,
        }}
      >
        {BENEFITS.map(({ icon: Icon, titleKey, descKey, color, bg, border }) => (
          <Box
            key={titleKey}
            sx={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 1.5,
              p: 1.5,
              borderRadius: 2,
              background: bg,
              border: '1px solid',
              borderColor: border,
              transition: 'background 0.15s ease',
            }}
          >
            <Box
              sx={{
                flexShrink: 0,
                width: 34,
                height: 34,
                borderRadius: 1.5,
                bgcolor: 'rgba(255,255,255,0.05)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Icon size={16} color={color} strokeWidth={2} />
            </Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography
                variant="body2"
                sx={{
                  fontWeight: 600,
                  fontSize: '0.8125rem',
                  color: 'text.primary',
                  lineHeight: 1.3,
                  mb: 0.25,
                }}
              >
                {t(titleKey)}
              </Typography>
              <Typography
                variant="caption"
                sx={{
                  color: 'text.secondary',
                  fontSize: '0.75rem',
                  lineHeight: 1.5,
                  display: 'block',
                }}
              >
                {t(descKey)}
              </Typography>
            </Box>
          </Box>
        ))}
      </Stack>

      {/* Actions */}
      <Box
        sx={{
          px: { xs: 2.5, sm: 3 },
          pb: { xs: 3, sm: 3 },
          pt: 0.5,
        }}
      >
        <Button
          onClick={handleSubmit}
          disabled={isPending}
          fullWidth
          variant="contained"
          size="large"
          startIcon={isPending ? null : <Fingerprint size={18} />}
          sx={{
            mb: 1.5,
            minHeight: 48,
            fontWeight: 600,
            fontSize: '0.9375rem',
            letterSpacing: '0.01em',
            borderRadius: 2.5,
            background: isPending ? undefined : 'linear-gradient(135deg, #16a34a 0%, #15803d 100%)',
            color: isPending ? undefined : '#fff',
            boxShadow: isPending ? undefined : '0 4px 16px rgba(22, 163, 74, 0.3)',
            '&:hover': {
              background: 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)',
              boxShadow: '0 4px 20px rgba(22, 163, 74, 0.4)',
            },
            transition: 'all 0.2s ease',
          }}
        >
          {isPending ? (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <CircularProgress size={16} thickness={5} sx={{ color: 'inherit' }} />
              <span>{t('settings.account.security.passkeyPromptConfirm')}</span>
            </Box>
          ) : (
            t('settings.account.security.passkeyPromptConfirm')
          )}
        </Button>

        <Stack direction="row" spacing={1}>
          <Button
            onClick={handleClose}
            disabled={isPending}
            fullWidth
            variant="outlined"
            size="medium"
            sx={{
              minHeight: 40,
              borderRadius: 2,
              borderColor: 'rgba(255,255,255,0.1)',
              color: 'text.secondary',
              fontSize: '0.8125rem',
              '&:hover': {
                borderColor: 'rgba(255,255,255,0.2)',
                bgcolor: 'rgba(255,255,255,0.04)',
              },
            }}
          >
            {t('settings.account.security.passkeyPromptSnooze')}
          </Button>
          <Button
            onClick={handleIgnore}
            disabled={isPending}
            fullWidth
            variant="text"
            size="medium"
            sx={{
              minHeight: 40,
              borderRadius: 2,
              color: 'text.disabled',
              fontSize: '0.8125rem',
              '&:hover': {
                bgcolor: 'rgba(255,255,255,0.03)',
                color: 'text.secondary',
              },
            }}
          >
            {t('settings.account.security.passkeyPromptIgnore')}
          </Button>
        </Stack>
      </Box>
    </ResponsiveDialog>
  )
}
