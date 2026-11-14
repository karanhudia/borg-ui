import { Box, Button, Chip, IconButton, Stack, Tooltip, Typography, alpha } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import { useState } from 'react'
import { Copy, Eye, EyeOff, KeyRound, Plus, Trash2 } from 'lucide-react'
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
  const [revealed, setRevealed] = useState<Set<number>>(() => new Set())
  const toggleRevealed = (id: number) =>
    setRevealed((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

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
          {keys.map((key) => {
            const visible = revealed.has(key.id)
            const revealLabel = visible
              ? t('sshConnections.systemKey.tooltips.hideFingerprint')
              : t('sshConnections.systemKey.tooltips.revealFingerprint')
            return (
              <Box
                component="li"
                key={key.id}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  pl: 2,
                  pr: 1,
                  py: 1.25,
                  borderRadius: 1.5,
                  border: '1px solid',
                  borderColor: 'divider',
                }}
              >
                <Box sx={{ minWidth: 0, flex: 1 }}>
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}>
                    <Typography noWrap sx={{ fontWeight: 600, minWidth: 0 }} title={key.name}>
                      {key.name}
                    </Typography>
                    <Chip
                      size="small"
                      variant="outlined"
                      label={key.key_type.toUpperCase()}
                      sx={{ height: 20, fontSize: '0.7rem', flexShrink: 0 }}
                    />
                    <Typography
                      variant="caption"
                      noWrap
                      sx={{
                        flexShrink: 0,
                        color: key.connection_count > 0 ? 'primary.main' : 'text.secondary',
                        fontWeight: key.connection_count > 0 ? 600 : 400,
                      }}
                    >
                      {key.connection_count > 0
                        ? t('sshConnections.extraKeys.connections', { count: key.connection_count })
                        : key.sftp_repository_count
                          ? t('sshConnections.extraKeys.mirrors', {
                              count: key.sftp_repository_count,
                            })
                          : t('sshConnections.extraKeys.unused')}
                    </Typography>
                  </Stack>
                  {key.fingerprint && (
                    <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', mt: 0.25 }}>
                      <Typography
                        noWrap
                        title={visible ? key.fingerprint : undefined}
                        sx={{
                          fontFamily: 'monospace',
                          fontSize: '0.75rem',
                          color: 'text.secondary',
                          minWidth: 0,
                          filter: visible ? 'none' : 'blur(4px)',
                          userSelect: visible ? 'auto' : 'none',
                          transition: 'filter 0.2s ease',
                        }}
                      >
                        {key.fingerprint}
                      </Typography>
                      <Tooltip title={revealLabel} arrow>
                        <IconButton
                          size="small"
                          aria-label={`${revealLabel}: ${key.name}`}
                          onClick={() => toggleRevealed(key.id)}
                          sx={{ p: 0.25, color: 'text.secondary' }}
                        >
                          {visible ? <EyeOff size={13} /> : <Eye size={13} />}
                        </IconButton>
                      </Tooltip>
                    </Stack>
                  )}
                </Box>
                <Tooltip title={t('sshConnections.extraKeys.copyPublicKey')} arrow>
                  <IconButton
                    aria-label={`${t('sshConnections.extraKeys.copyPublicKey')}: ${key.name}`}
                    onClick={() => onCopyPublicKey(key)}
                    sx={{ color: 'text.secondary' }}
                  >
                    <Copy size={16} />
                  </IconButton>
                </Tooltip>
                <Tooltip title={t('sshConnections.extraKeys.delete')} arrow>
                  <IconButton
                    aria-label={`${t('sshConnections.extraKeys.delete')}: ${key.name}`}
                    onClick={() => onDelete(key)}
                    sx={{
                      color: 'text.secondary',
                      '&:hover': {
                        color: 'error.main',
                        bgcolor: alpha(theme.palette.error.main, 0.08),
                      },
                    }}
                  >
                    <Trash2 size={16} />
                  </IconButton>
                </Tooltip>
              </Box>
            )
          })}
        </Stack>
      )}
    </Box>
  )
}
