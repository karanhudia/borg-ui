import {
  Box,
  Button,
  FormControlLabel,
  IconButton,
  Stack,
  Switch,
  Tooltip,
  Typography,
} from '@mui/material'
import { AlertTriangle, Check, Copy, Key } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface MetricsAccessSectionProps {
  metricsEnabled: boolean
  metricsRequireAuth: boolean
  rotateMetricsToken: boolean
  metricsTokenSet?: boolean
  newMetricsToken: string | null
  metricsTokenCopied: boolean
  setMetricsEnabled: (value: boolean) => void
  setMetricsRequireAuth: (value: boolean) => void
  setRotateMetricsToken: (value: boolean) => void
  onCopyMetricsToken: () => void
}

const MetricsAccessSection: React.FC<MetricsAccessSectionProps> = ({
  metricsEnabled,
  metricsRequireAuth,
  rotateMetricsToken,
  metricsTokenSet,
  newMetricsToken,
  metricsTokenCopied,
  setMetricsEnabled,
  setMetricsRequireAuth,
  setRotateMetricsToken,
  onCopyMetricsToken,
}) => {
  const { t } = useTranslation()

  return (
    <Stack spacing={2}>
      <FormControlLabel
        control={
          <Switch
            checked={metricsEnabled}
            onChange={(e) => {
              const enabled = e.target.checked
              setMetricsEnabled(enabled)
              if (!enabled) {
                setMetricsRequireAuth(false)
                setRotateMetricsToken(false)
              }
            }}
          />
        }
        label={t('systemSettings.metricsEnabledLabel')}
      />

      <FormControlLabel
        control={
          <Switch
            checked={metricsRequireAuth}
            disabled={!metricsEnabled}
            onChange={(e) => {
              const enabled = e.target.checked
              setMetricsRequireAuth(enabled)
              if (!enabled) {
                setRotateMetricsToken(false)
              }
            }}
          />
        }
        label={t('systemSettings.metricsRequireAuthLabel')}
      />

      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', md: 'row' },
          gap: 1.5,
          alignItems: { xs: 'stretch', md: 'center' },
        }}
      >
        <Button
          variant="outlined"
          startIcon={<Key size={16} />}
          disabled={!metricsEnabled || !metricsRequireAuth}
          onClick={() => setRotateMetricsToken(true)}
        >
          {metricsTokenSet
            ? t('systemSettings.metricsRotateToken')
            : t('systemSettings.metricsGenerateToken')}
        </Button>
        <Typography variant="body2" color="text.secondary">
          {!metricsEnabled || !metricsRequireAuth
            ? t('systemSettings.metricsTokenDisabledHelper')
            : rotateMetricsToken
              ? t('systemSettings.metricsTokenWillRotate')
              : metricsTokenSet
                ? t('systemSettings.metricsTokenConfigured')
                : t('systemSettings.metricsTokenWillGenerate')}
        </Typography>
      </Box>

      {newMetricsToken && (
        <Box
          sx={{
            p: 2,
            borderRadius: 2,
            border: '1px solid',
            borderColor: 'success.main',
            bgcolor: 'rgba(76, 175, 80, 0.06)',
          }}
        >
          <Stack spacing={1.5}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
              <AlertTriangle size={13} color="orange" />
              <Typography variant="caption" fontWeight={600} color="warning.main">
                {t('systemSettings.metricsTokenDialogWarning')}
              </Typography>
            </Box>
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                px: 1.5,
                py: 1,
                borderRadius: 1.5,
                bgcolor: 'background.default',
                border: '1px solid',
                borderColor: 'divider',
              }}
            >
              <Typography
                sx={{
                  flex: 1,
                  fontFamily: 'monospace',
                  fontSize: '0.78rem',
                  color: 'text.primary',
                  wordBreak: 'break-all',
                  lineHeight: 1.6,
                  userSelect: 'all',
                }}
              >
                {newMetricsToken}
              </Typography>
              <Tooltip
                title={
                  metricsTokenCopied
                    ? t('systemSettings.metricsTokenCopied')
                    : t('common.buttons.copy')
                }
              >
                <IconButton
                  size="small"
                  onClick={onCopyMetricsToken}
                  color={metricsTokenCopied ? 'success' : 'default'}
                  sx={{ flexShrink: 0 }}
                >
                  {metricsTokenCopied ? <Check size={15} /> : <Copy size={15} />}
                </IconButton>
              </Tooltip>
            </Box>
          </Stack>
        </Box>
      )}
    </Stack>
  )
}

export default MetricsAccessSection
