import { Alert, Box, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

import type { AuthConfigResponse } from '../../services/api'

interface ProxyAuthSectionProps {
  proxyAuthConfig?: AuthConfigResponse
  proxyAuthHeaderRows: Array<[string, string | null | undefined]>
}

const ProxyAuthSection: React.FC<ProxyAuthSectionProps> = ({
  proxyAuthConfig,
  proxyAuthHeaderRows,
}) => {
  const { t } = useTranslation()

  return (
    <Stack spacing={2}>
      <Alert severity={proxyAuthConfig?.proxy_auth_enabled ? 'info' : 'success'} variant="outlined">
        <Typography variant="body2">
          {proxyAuthConfig?.proxy_auth_enabled
            ? t('systemSettings.proxyAuthEnabledStatus')
            : t('systemSettings.proxyAuthDisabledStatus')}
        </Typography>
      </Alert>

      {proxyAuthConfig?.proxy_auth_enabled ? (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
            gap: 2,
          }}
        >
          {proxyAuthHeaderRows.map(([labelKey, value]) => (
            <Box
              key={labelKey}
              sx={{
                p: 2,
                borderRadius: 2,
                border: '1px solid',
                borderColor: 'divider',
              }}
            >
              <Typography variant="caption" color="text.secondary">
                {t(labelKey)}
              </Typography>
              <Typography
                variant="body2"
                sx={{ mt: 0.5, fontFamily: 'monospace', wordBreak: 'break-word' }}
              >
                {value || t('systemSettings.proxyAuthNotConfigured')}
              </Typography>
            </Box>
          ))}
        </Box>
      ) : null}

      {proxyAuthConfig?.proxy_auth_health?.warnings?.length ? (
        <Alert severity="warning">
          <Typography variant="body2" fontWeight={600} sx={{ mb: 1 }}>
            {t('systemSettings.proxyAuthWarningsTitle')}
          </Typography>
          <Stack spacing={0.75}>
            {proxyAuthConfig.proxy_auth_health.warnings.map((warning) => (
              <Typography key={warning.code} variant="body2">
                • {warning.message}
              </Typography>
            ))}
          </Stack>
        </Alert>
      ) : proxyAuthConfig?.proxy_auth_enabled ? (
        <Alert severity="success">
          <Typography variant="body2">{t('systemSettings.proxyAuthNoWarnings')}</Typography>
        </Alert>
      ) : null}
    </Stack>
  )
}

export default ProxyAuthSection
