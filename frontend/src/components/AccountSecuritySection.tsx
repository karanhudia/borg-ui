import { Box, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { Lock } from 'lucide-react'

interface AccountSecuritySectionProps {
  mustChangePassword: boolean
  onOpenChangePassword: () => void
}

export default function AccountSecuritySection({
  mustChangePassword,
  onOpenChangePassword,
}: AccountSecuritySectionProps) {
  const { t } = useTranslation()

  return (
    <Box
      onClick={onOpenChangePassword}
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
        borderColor: mustChangePassword ? 'rgba(245,158,11,0.35)' : 'rgba(255,255,255,0.07)',
        background: mustChangePassword
          ? 'linear-gradient(135deg, rgba(120,53,15,0.18) 0%, rgba(146,64,14,0.10) 100%)'
          : 'linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)',
        transition: 'border-color 180ms ease, background 180ms ease',
        '&:hover': {
          borderColor: mustChangePassword ? 'rgba(245,158,11,0.6)' : 'rgba(255,255,255,0.14)',
          background: mustChangePassword
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
            background: mustChangePassword
              ? 'linear-gradient(135deg, #92400e 0%, #b45309 100%)'
              : 'linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.03) 100%)',
            border: '1px solid',
            borderColor: mustChangePassword ? 'rgba(245,158,11,0.4)' : 'rgba(255,255,255,0.08)',
          }}
        >
          <Lock
            size={16}
            style={{
              color: mustChangePassword ? '#fde68a' : undefined,
              opacity: mustChangePassword ? 1 : 0.45,
            }}
          />
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="body2" fontWeight={600} noWrap>
            {mustChangePassword
              ? t('settings.account.security.passwordUpdateRequired')
              : t('settings.account.security.accountPassword')}
          </Typography>
          <Typography variant="caption" color="text.secondary" noWrap>
            {mustChangePassword
              ? t('settings.account.security.passwordUpdateHint')
              : t('settings.account.security.changeCredentialsHint')}
          </Typography>
        </Box>
      </Stack>
      <Box
        sx={{
          fontSize: '0.75rem',
          fontWeight: 600,
          color: mustChangePassword ? '#fbbf24' : 'text.secondary',
          flexShrink: 0,
          opacity: 0.7,
          letterSpacing: '0.02em',
        }}
      >
        {mustChangePassword ? `${t('settings.account.security.updateLink')} →` : '→'}
      </Box>
    </Box>
  )
}
