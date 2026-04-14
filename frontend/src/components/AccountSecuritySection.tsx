import { Box, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { Lock } from 'lucide-react'

interface AccountSecuritySectionProps {
  onOpenChangePassword: () => void
}

export default function AccountSecuritySection({
  onOpenChangePassword,
}: AccountSecuritySectionProps) {
  const { t } = useTranslation()
  const title = t('settings.account.security.accountPassword')
  const description = t('settings.account.security.changeCredentialsHint')

  return (
    <Box
      onClick={onOpenChangePassword}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onOpenChangePassword()
        }
      }}
      role="button"
      tabIndex={0}
      aria-label={title}
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
            border: '1px solid',
            borderColor: 'rgba(255,255,255,0.08)',
          }}
        >
          <Lock size={16} style={{ opacity: 0.45 }} />
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="body2" fontWeight={600} noWrap>
            {title}
          </Typography>
          <Typography variant="caption" color="text.secondary" noWrap>
            {description}
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
          letterSpacing: '0.02em',
        }}
      >
        →
      </Box>
    </Box>
  )
}
