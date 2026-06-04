import { Box, Button, IconButton, Stack, Typography, useTheme } from '@mui/material'
import { KeyRound, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { PasskeyCredentialResponse } from '../services/api'

interface AccountPasskeysSectionProps {
  passkeys: PasskeyCredentialResponse[]
  loading: boolean
  onAdd: () => void
  onDelete: (passkeyId: number) => void
}

export default function AccountPasskeysSection({
  passkeys,
  loading,
  onAdd,
  onDelete,
}: AccountPasskeysSectionProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const cardGradient = isDark
    ? 'linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)'
    : 'linear-gradient(135deg, rgba(0,0,0,0.015) 0%, rgba(0,0,0,0.005) 100%)'
  const neutralIconBg = isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)'

  return (
    <Box>
      <Typography variant="subtitle2" fontWeight={700} gutterBottom>
        {t('settings.account.security.passkeysTitle')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t('settings.account.security.passkeysDescription')}
      </Typography>
      <Box
        sx={{
          p: 2.5,
          mb: 1.5,
          borderRadius: 2.5,
          border: '1px solid',
          borderColor: passkeys.length > 0 ? 'rgba(59,130,246,0.2)' : 'divider',
          background:
            passkeys.length > 0
              ? 'linear-gradient(135deg, rgba(59,130,246,0.08) 0%, rgba(14,116,144,0.05) 100%)'
              : cardGradient,
        }}
      >
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={2}
          justifyContent="space-between"
          alignItems={{ xs: 'flex-start', md: 'center' }}
        >
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Box
              sx={{
                width: 40,
                height: 40,
                borderRadius: 2,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                bgcolor: passkeys.length > 0 ? 'rgba(59,130,246,0.16)' : neutralIconBg,
              }}
            >
              <KeyRound size={18} />
            </Box>
            <Box>
              <Typography
                variant="caption"
                sx={{
                  display: 'block',
                  mb: 0.35,
                  fontWeight: 700,
                  letterSpacing: '0.04em',
                  textTransform: 'uppercase',
                  color: passkeys.length > 0 ? 'info.light' : 'text.secondary',
                }}
              >
                {passkeys.length > 0
                  ? t('settings.account.security.statusReady')
                  : t('settings.account.security.statusNotConfigured')}
              </Typography>
              <Typography variant="body2" fontWeight={700}>
                {passkeys.length > 0
                  ? t('settings.account.security.passkeysCount', { count: passkeys.length })
                  : t('settings.account.security.noPasskeys')}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {passkeys.length > 0
                  ? t('settings.account.security.passkeysManageHint')
                  : t('settings.account.security.passkeyEmptyHint')}
              </Typography>
            </Box>
          </Stack>

          <Button
            variant="outlined"
            onClick={onAdd}
            disabled={loading}
            sx={{
              minWidth: { xs: '100%', md: 'auto' },
              alignSelf: { md: 'center' },
              whiteSpace: 'nowrap',
            }}
          >
            {t('settings.account.security.addPasskey')}
          </Button>
        </Stack>
      </Box>

      <Stack spacing={1.5}>
        {passkeys.length > 0 &&
          passkeys.map((passkey) => (
            <Box
              key={passkey.id}
              sx={{
                p: 2,
                borderRadius: 2,
                border: '1px solid',
                borderColor: 'divider',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 2,
              }}
            >
              <Stack direction="row" spacing={1.5} alignItems="center">
                <KeyRound size={16} />
                <Box>
                  <Typography variant="body2" fontWeight={600}>
                    {passkey.name}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {passkey.last_used_at
                      ? t('settings.account.security.passkeyLastUsed', {
                          date: new Date(passkey.last_used_at).toLocaleString(),
                        })
                      : t('settings.account.security.passkeyNeverUsed')}
                  </Typography>
                </Box>
              </Stack>
              <IconButton
                aria-label={t('common.buttons.delete')}
                onClick={() => onDelete(passkey.id)}
                disabled={loading}
              >
                <Trash2 size={16} />
              </IconButton>
            </Box>
          ))}
      </Stack>
    </Box>
  )
}
