import { Box, Button, Stack, Typography } from '@mui/material'
import { KeyRound, ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface AccountTotpSectionProps {
  enabled: boolean
  recoveryCodesRemaining: number
  loading: boolean
  onEnable: () => void
  onDisable: () => void
}

export default function AccountTotpSection({
  enabled,
  recoveryCodesRemaining,
  loading,
  onEnable,
  onDisable,
}: AccountTotpSectionProps) {
  const { t } = useTranslation()

  return (
    <Box>
      <Typography variant="subtitle2" fontWeight={700} gutterBottom>
        {t('settings.account.security.totpTitle')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t('settings.account.security.totpDescription')}
      </Typography>

      <Box
        sx={{
          p: 2.5,
          borderRadius: 2.5,
          border: '1px solid',
          borderColor: enabled ? 'rgba(34,197,94,0.25)' : 'divider',
          background: enabled
            ? 'linear-gradient(135deg, rgba(34,197,94,0.08) 0%, rgba(14,116,144,0.05) 100%)'
            : 'linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)',
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
                bgcolor: enabled ? 'rgba(34,197,94,0.16)' : 'rgba(255,255,255,0.04)',
              }}
            >
              {enabled ? <ShieldCheck size={18} /> : <KeyRound size={18} />}
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
                  color: enabled ? 'success.light' : 'text.disabled',
                }}
              >
                {enabled
                  ? t('settings.account.security.statusActive')
                  : t('settings.account.security.statusNotEnabled')}
              </Typography>
              <Typography variant="body2" fontWeight={700}>
                {enabled
                  ? t('settings.account.security.totpEnabled')
                  : t('settings.account.security.totpDisabled')}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {enabled
                  ? t('settings.account.security.recoveryCodesRemaining', {
                      count: recoveryCodesRemaining,
                    })
                  : t('settings.account.security.totpDisabledHint')}
              </Typography>
            </Box>
          </Stack>

          <Stack
            direction="row"
            spacing={1}
            flexWrap="wrap"
            sx={{ width: { xs: '100%', md: 'auto' }, alignSelf: { md: 'center' } }}
          >
            <Button
              variant={enabled ? 'outlined' : 'contained'}
              onClick={enabled ? onDisable : onEnable}
              disabled={loading}
              sx={{ minWidth: { xs: '100%', sm: 160, md: 'auto' } }}
            >
              {enabled
                ? t('settings.account.security.disableTotp')
                : t('settings.account.security.enableTotp')}
            </Button>
          </Stack>
        </Stack>
      </Box>
    </Box>
  )
}
