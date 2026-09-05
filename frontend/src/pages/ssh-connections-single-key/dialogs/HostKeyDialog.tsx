import type { TFunction } from 'i18next'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from '@mui/material'
import type { SSHHostKeyResponse } from '../../../services/api'
import type { SSHConnection } from '../types'

interface HostKeyDialogProps {
  t: TFunction
  open: boolean
  onClose: () => void
  connection: SSHConnection | null
  hostKey?: SSHHostKeyResponse | null
  loading: boolean
  pending: boolean
  onTrust: () => void
  onForget: () => void
}

const FINGERPRINT_SX = {
  fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
  fontSize: '0.78rem',
  wordBreak: 'break-all' as const,
}

/**
 * Shows what host key a connection trusts and what the host offers right now,
 * so the fingerprint can be compared against the host itself before it is
 * pinned. This is OpenSSH's first-connect question, asked in the UI.
 */
export function HostKeyDialog({
  t,
  open,
  onClose,
  connection,
  hostKey,
  loading,
  pending,
  onTrust,
  onForget,
}: HostKeyDialogProps) {
  const status = hostKey?.status
  const canTrust = status === 'unknown' || status === 'changed'

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('sshConnections.hostKeyDialog.title')}</DialogTitle>
      <DialogContent>
        {connection && (
          <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
            {t('sshConnections.hostKeyDialog.subtitle', {
              host: connection.host,
              port: connection.port,
            })}
          </Typography>
        )}

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
            <CircularProgress size={24} />
          </Box>
        ) : (
          <Stack spacing={2}>
            {status === 'changed' && (
              <Alert severity="error" data-testid="host-key-changed">
                {t('sshConnections.hostKeyDialog.changed')}
              </Alert>
            )}
            {status === 'unknown' && (
              <Alert severity="warning">{t('sshConnections.hostKeyDialog.unknown')}</Alert>
            )}
            {status === 'trusted' && (
              <Alert severity="success">{t('sshConnections.hostKeyDialog.trusted')}</Alert>
            )}
            {status === 'unreachable' && (
              <Alert severity="info">{t('sshConnections.hostKeyDialog.unreachable')}</Alert>
            )}

            {hostKey?.trusted_fingerprint && (
              <Box>
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  {t('sshConnections.hostKeyDialog.trustedFingerprint')}
                </Typography>
                <Typography sx={FINGERPRINT_SX}>{hostKey.trusted_fingerprint}</Typography>
              </Box>
            )}

            {hostKey?.observed_fingerprint && (
              <Box>
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  {t('sshConnections.hostKeyDialog.observedFingerprint')}
                </Typography>
                <Typography sx={FINGERPRINT_SX}>{hostKey.observed_fingerprint}</Typography>
              </Box>
            )}

            {canTrust && (
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {t('sshConnections.hostKeyDialog.compareHint')}
              </Typography>
            )}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.buttons.cancel')}</Button>
        {status === 'trusted' && (
          <Button color="warning" onClick={onForget} disabled={pending}>
            {t('sshConnections.hostKeyDialog.forget')}
          </Button>
        )}
        {canTrust && (
          <Button
            variant="contained"
            color={status === 'changed' ? 'error' : 'primary'}
            onClick={onTrust}
            disabled={pending || !hostKey?.observed_key}
          >
            {status === 'changed'
              ? t('sshConnections.hostKeyDialog.trustNewKey')
              : t('sshConnections.hostKeyDialog.trust')}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  )
}
