import { Box, Button, Chip, IconButton, Stack, Tooltip, Typography, alpha } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import { Copy, KeyRound, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { SSHKeySummary } from '../types'

interface ExtraKeysCardProps {
  /** Keys other than the system key. */
  keys: SSHKeySummary[]
  onAdd: () => void
  onCopyPublicKey: (key: SSHKeySummary) => void
  onDelete: (key: SSHKeySummary) => void
}

export function ExtraKeysCard({ keys, onAdd, onCopyPublicKey, onDelete }: ExtraKeysCardProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  return (
    <Box
      sx={{
        borderRadius: 2,
        bgcolor: 'background.paper',
        mb: 3,
        px: { xs: 2, sm: 2.5 },
        py: { xs: 2, sm: 2.5 },
        boxShadow: isDark
          ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
          : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
      }}
    >
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 0.5 }}>
        <Box
          sx={{
            width: 34,
            height: 34,
            borderRadius: 1.5,
            bgcolor: alpha(theme.palette.primary.main, isDark ? 0.15 : 0.1),
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: theme.palette.primary.main,
            flexShrink: 0,
          }}
        >
          <KeyRound size={18} />
        </Box>
        <Typography variant="h6" sx={{ fontWeight: 600, flex: 1, minWidth: 0 }}>
          {t('sshConnections.extraKeys.title')}
        </Typography>
        <Button variant="outlined" size="small" startIcon={<Plus size={16} />} onClick={onAdd}>
          {t('sshConnections.extraKeys.add')}
        </Button>
      </Stack>
      <Typography variant="body2" sx={{ color: 'text.secondary', mb: keys.length ? 2 : 0 }}>
        {t('sshConnections.extraKeys.description')}
      </Typography>

      {keys.length === 0 ? (
        <Typography variant="body2" sx={{ color: 'text.disabled', mt: 1.5 }}>
          {t('sshConnections.extraKeys.empty')}
        </Typography>
      ) : (
        <Stack spacing={1} component="ul" sx={{ listStyle: 'none', m: 0, p: 0 }}>
          {keys.map((key) => (
            <Box
              component="li"
              key={key.id}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1.5,
                px: 1.5,
                py: 1,
                borderRadius: 1.5,
                border: '1px solid',
                borderColor: 'divider',
              }}
            >
              <Box sx={{ minWidth: 0, flex: 1 }}>
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                  <Typography noWrap sx={{ fontWeight: 600, minWidth: 0 }} title={key.name}>
                    {key.name}
                  </Typography>
                  <Chip size="small" variant="outlined" label={key.key_type.toUpperCase()} />
                  <Chip
                    size="small"
                    variant="outlined"
                    color={key.connection_count > 0 ? 'primary' : 'default'}
                    label={
                      key.connection_count > 0
                        ? t('sshConnections.extraKeys.connections', { count: key.connection_count })
                        : t('sshConnections.extraKeys.unused')
                    }
                  />
                </Stack>
                {key.fingerprint && (
                  <Typography
                    noWrap
                    title={key.fingerprint}
                    sx={{
                      fontFamily: 'monospace',
                      fontSize: '0.72rem',
                      color: 'text.secondary',
                    }}
                  >
                    {key.fingerprint}
                  </Typography>
                )}
              </Box>
              <Tooltip title={t('sshConnections.extraKeys.copyPublicKey')} arrow>
                <IconButton
                  aria-label={`${t('sshConnections.extraKeys.copyPublicKey')}: ${key.name}`}
                  onClick={() => onCopyPublicKey(key)}
                >
                  <Copy size={16} />
                </IconButton>
              </Tooltip>
              <Tooltip title={t('sshConnections.extraKeys.delete')} arrow>
                <IconButton
                  aria-label={`${t('sshConnections.extraKeys.delete')}: ${key.name}`}
                  color="error"
                  onClick={() => onDelete(key)}
                >
                  <Trash2 size={16} />
                </IconButton>
              </Tooltip>
            </Box>
          ))}
        </Stack>
      )}
    </Box>
  )
}
