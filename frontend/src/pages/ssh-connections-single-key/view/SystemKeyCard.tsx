import type { Dispatch, SetStateAction } from 'react'
import type { TFunction } from 'i18next'
import type { Theme } from '@mui/material/styles'
import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
  Stack,
  Tooltip,
  Typography,
  alpha,
} from '@mui/material'
import { CheckCircle, Copy, Eye, EyeOff, Key, Plus, Trash2, Wifi } from 'lucide-react'
import type { SystemSSHKey } from '../types'

interface SystemKeyCardProps {
  t: TFunction
  theme: Theme
  isDark: boolean
  keyExists: boolean | undefined
  systemKey: SystemSSHKey | undefined
  keyVisible: boolean
  setKeyVisible: Dispatch<SetStateAction<boolean>>
  fingerprintVisible: boolean
  setFingerprintVisible: Dispatch<SetStateAction<boolean>>
  setGenerateDialogOpen: Dispatch<SetStateAction<boolean>>
  setImportDialogOpen: Dispatch<SetStateAction<boolean>>
  setDeployDialogOpen: Dispatch<SetStateAction<boolean>>
  setTestConnectionDialogOpen: Dispatch<SetStateAction<boolean>>
  setDeleteKeyDialogOpen: Dispatch<SetStateAction<boolean>>
  onCopyPublicKey: () => void
}

export function SystemKeyCard({
  t,
  theme,
  isDark,
  keyExists,
  systemKey,
  keyVisible,
  setKeyVisible,
  fingerprintVisible,
  setFingerprintVisible,
  setGenerateDialogOpen,
  setImportDialogOpen,
  setDeployDialogOpen,
  setTestConnectionDialogOpen,
  setDeleteKeyDialogOpen,
  onCopyPublicKey,
}: SystemKeyCardProps) {
  return (
    <Box
      sx={{
        borderRadius: 2,
        bgcolor: 'background.paper',
        overflow: 'hidden',
        mb: 3,
        boxShadow: isDark
          ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
          : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
      }}
    >
      <Box sx={{ px: { xs: 2, sm: 2.5 }, pt: { xs: 2, sm: 2.5 }, pb: { xs: 2, sm: 2.5 } }}>
        <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 2 }}>
          <Box
            sx={{
              width: 34,
              height: 34,
              borderRadius: 1.5,
              bgcolor: isDark
                ? alpha(theme.palette.primary.main, 0.15)
                : alpha(theme.palette.primary.main, 0.1),
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: theme.palette.primary.main,
              flexShrink: 0,
            }}
          >
            <Key size={18} />
          </Box>
          <Typography variant="h6" fontWeight={600} sx={{ flex: 1 }}>
            {t('sshConnections.systemKey.title')}
          </Typography>
          {keyExists && (
            <Chip
              label={t('common.active')}
              color="success"
              size="small"
              icon={<CheckCircle size={14} />}
            />
          )}
        </Stack>

        {!keyExists ? (
          <Box>
            <Alert severity="warning" sx={{ mb: 2 }}>
              {t('sshConnections.systemKey.noKey')}
            </Alert>
            <Stack direction="row" spacing={2}>
              <Button
                variant="contained"
                startIcon={<Plus size={18} />}
                onClick={() => setGenerateDialogOpen(true)}
              >
                {t('sshConnections.systemKey.generate')}
              </Button>
              <Button
                variant="outlined"
                startIcon={<Key size={18} />}
                onClick={() => setImportDialogOpen(true)}
              >
                {t('sshConnections.systemKey.import')}
              </Button>
            </Stack>
          </Box>
        ) : (
          <Box>
            <Stack spacing={2}>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  {t('sshConnections.systemKey.type')}
                </Typography>
                <Typography variant="body2" fontWeight={500}>
                  {systemKey?.key_type?.toUpperCase() || t('common.unknown')}
                </Typography>
              </Box>

              {systemKey?.fingerprint && (
                <Box>
                  <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mb: 0.25 }}>
                    <Typography variant="caption" color="text.secondary">
                      {t('sshConnections.systemKey.fingerprint')}
                    </Typography>
                    <Tooltip
                      title={
                        fingerprintVisible
                          ? t('sshConnections.systemKey.tooltips.hideFingerprint')
                          : t('sshConnections.systemKey.tooltips.revealFingerprint')
                      }
                    >
                      <IconButton
                        size="small"
                        aria-label={
                          fingerprintVisible
                            ? t('sshConnections.systemKey.tooltips.hideFingerprint')
                            : t('sshConnections.systemKey.tooltips.revealFingerprint')
                        }
                        onClick={() => setFingerprintVisible((v) => !v)}
                        sx={{ p: 0.25 }}
                      >
                        {fingerprintVisible ? <EyeOff size={13} /> : <Eye size={13} />}
                      </IconButton>
                    </Tooltip>
                  </Stack>
                  <Typography
                    variant="body2"
                    fontWeight={500}
                    sx={{
                      fontFamily: 'monospace',
                      fontSize: '0.85rem',
                      wordBreak: 'break-all',
                      filter: fingerprintVisible ? 'none' : 'blur(4px)',
                      userSelect: fingerprintVisible ? 'auto' : 'none',
                      transition: 'filter 0.2s ease',
                    }}
                  >
                    {systemKey.fingerprint}
                  </Typography>
                </Box>
              )}

              <Box>
                <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mb: 0.5 }}>
                  <Typography variant="caption" color="text.secondary">
                    {t('sshConnections.systemKey.publicKey')}
                  </Typography>
                  <Tooltip
                    title={
                      keyVisible
                        ? t('sshConnections.systemKey.tooltips.hideKey')
                        : t('sshConnections.systemKey.tooltips.revealKey')
                    }
                  >
                    <IconButton
                      size="small"
                      aria-label={
                        keyVisible
                          ? t('sshConnections.systemKey.tooltips.hideKey')
                          : t('sshConnections.systemKey.tooltips.revealKey')
                      }
                      onClick={() => setKeyVisible((v) => !v)}
                      sx={{ p: 0.25 }}
                    >
                      {keyVisible ? <EyeOff size={13} /> : <Eye size={13} />}
                    </IconButton>
                  </Tooltip>
                </Stack>
                <Box
                  sx={{
                    position: 'relative',
                    bgcolor: 'background.default',
                    p: 1.5,
                    pr: 5,
                    borderRadius: 1,
                    border: '1px solid',
                    borderColor: 'divider',
                  }}
                >
                  <Typography
                    variant="body2"
                    sx={{
                      fontFamily: 'monospace',
                      fontSize: '0.75rem',
                      wordBreak: 'break-all',
                      maxHeight: '100px',
                      overflow: 'auto',
                      filter: keyVisible ? 'none' : 'blur(4px)',
                      userSelect: keyVisible ? 'auto' : 'none',
                      transition: 'filter 0.2s ease',
                    }}
                  >
                    {systemKey?.public_key || t('common.na')}
                  </Typography>
                  <Box sx={{ position: 'absolute', top: 6, right: 6 }}>
                    <Tooltip title={t('sshConnections.systemKey.tooltips.copyToClipboard')}>
                      <IconButton
                        size="small"
                        aria-label={t('sshConnections.systemKey.tooltips.copyToClipboard')}
                        onClick={onCopyPublicKey}
                      >
                        <Copy size={15} />
                      </IconButton>
                    </Tooltip>
                  </Box>
                </Box>
              </Box>

              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} flexWrap="wrap">
                <Tooltip title={t('sshConnections.systemKey.tooltips.deploy')}>
                  <Button
                    variant="contained"
                    startIcon={<Plus size={18} />}
                    onClick={() => setDeployDialogOpen(true)}
                    fullWidth={false}
                    sx={{ width: { xs: '100%', sm: 'auto' } }}
                  >
                    {t('sshConnections.systemKey.actions.deploy')}
                  </Button>
                </Tooltip>
                <Tooltip title={t('sshConnections.systemKey.tooltips.addManual')}>
                  <Button
                    variant="outlined"
                    startIcon={<Wifi size={18} />}
                    onClick={() => setTestConnectionDialogOpen(true)}
                    sx={{ width: { xs: '100%', sm: 'auto' } }}
                  >
                    {t('sshConnections.systemKey.actions.addManual')}
                  </Button>
                </Tooltip>
                <Tooltip title={t('sshConnections.systemKey.tooltips.delete')}>
                  <Button
                    variant="outlined"
                    color="error"
                    startIcon={<Trash2 size={18} />}
                    onClick={() => setDeleteKeyDialogOpen(true)}
                    sx={{ width: { xs: '100%', sm: 'auto' } }}
                  >
                    {t('sshConnections.systemKey.actions.delete')}
                  </Button>
                </Tooltip>
              </Stack>
            </Stack>
          </Box>
        )}
      </Box>
    </Box>
  )
}
