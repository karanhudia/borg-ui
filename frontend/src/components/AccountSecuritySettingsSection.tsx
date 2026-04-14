import { Box, Stack, Typography, useTheme } from '@mui/material'
import { KeyRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import AccountPasskeysSection from './AccountPasskeysSection'
import AccountTotpSection from './AccountTotpSection'
import type { PasskeyCredentialResponse } from '../services/api'

interface AccountSecuritySettingsSectionProps {
  totpEnabled: boolean
  recoveryCodesRemaining: number
  totpLoading: boolean
  onEnableTotp: () => void
  onDisableTotp: () => void
  passkeys: PasskeyCredentialResponse[]
  passkeysLoading: boolean
  onAddPasskey: () => void
  onDeletePasskey: (passkeyId: number) => void
}

export default function AccountSecuritySettingsSection({
  totpEnabled,
  recoveryCodesRemaining,
  totpLoading,
  onEnableTotp,
  onDisableTotp,
  passkeys,
  passkeysLoading,
  onAddPasskey,
  onDeletePasskey,
}: AccountSecuritySettingsSectionProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const neutralBg = isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)'
  const subtleBorder = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.09)'

  const securityHighlights = [
    {
      label: t('settings.account.security.highlights.twoFactor'),
      value: totpEnabled
        ? t('settings.account.security.statusActive')
        : t('settings.account.security.statusNotEnabled'),
      tone: totpEnabled ? 'rgba(34,197,94,0.14)' : neutralBg,
    },
    {
      label: t('settings.account.security.highlights.passkeys'),
      value:
        passkeys.length > 0
          ? t('settings.account.security.passkeysCount', { count: passkeys.length })
          : t('settings.account.security.statusNotConfigured'),
      tone: passkeys.length > 0 ? 'rgba(59,130,246,0.14)' : neutralBg,
    },
  ]

  return (
    <Stack spacing={3.5}>
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
              <KeyRound size={16} />
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
                {t('settings.account.security.overline')}
              </Typography>
              <Typography variant="h6" fontWeight={700} sx={{ lineHeight: 1.1 }}>
                {t('settings.account.security.title')}
              </Typography>
            </Box>
          </Stack>

          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ maxWidth: 720, fontSize: { md: '0.95rem' } }}
          >
            {t('settings.account.security.description')}
          </Typography>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' },
              gap: 1.5,
            }}
          >
            {securityHighlights.map((highlight) => (
              <Box
                key={highlight.label}
                sx={{
                  p: 1.75,
                  borderRadius: 2.5,
                  border: '1px solid',
                  borderColor: subtleBorder,
                  bgcolor: highlight.tone,
                  minHeight: 88,
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
                  {highlight.label}
                </Typography>
                <Typography variant="subtitle2" fontWeight={700}>
                  {highlight.value}
                </Typography>
              </Box>
            ))}
          </Box>
        </Stack>
      </Box>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', xl: 'repeat(2, minmax(0, 1fr))' },
          gap: 3,
          alignItems: 'start',
        }}
      >
        <AccountTotpSection
          enabled={totpEnabled}
          recoveryCodesRemaining={recoveryCodesRemaining}
          loading={totpLoading}
          onEnable={onEnableTotp}
          onDisable={onDisableTotp}
        />

        <AccountPasskeysSection
          passkeys={passkeys}
          loading={passkeysLoading}
          onAdd={onAddPasskey}
          onDelete={onDeletePasskey}
        />
      </Box>
    </Stack>
  )
}
