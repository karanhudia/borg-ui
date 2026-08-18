import { Box, Button, Stack, Tooltip, Typography } from '@mui/material'
import { alpha, keyframes } from '@mui/material/styles'
import { CheckCircle, Copy, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { AgentMachineResponse } from '../../services/api'
import {
  buildAgentInstallCommand,
  type AgentServiceUserMode,
  type BorgInstallMode,
} from './agentInstallCommandText'

const spin = keyframes`
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
`

export default function AgentInstallCommand({
  serverUrl,
  token,
  agentName,
  borgInstallMode = 'borg1',
  serviceUserMode = 'current',
  connectedAgent,
  onCopy,
}: {
  serverUrl: string
  token: string
  agentName: string
  borgInstallMode?: BorgInstallMode
  serviceUserMode?: AgentServiceUserMode
  connectedAgent?: AgentMachineResponse | null
  onCopy: (value: string) => void
}) {
  const { t } = useTranslation()
  const command = buildAgentInstallCommand(
    serverUrl,
    token,
    agentName,
    borgInstallMode,
    serviceUserMode
  )

  return (
    <Stack spacing={1.5}>
      <Typography
        variant="subtitle2"
        sx={{
          fontWeight: 700,
        }}
      >
        {t('managedAgents.installCommand.title')}
      </Typography>
      <Box sx={{ position: 'relative', minWidth: 0 }}>
        <Box
          component="code"
          sx={{
            display: 'block',
            p: 1.5,
            pr: 5.5,
            borderRadius: 1,
            border: '1px solid',
            borderColor: 'divider',
            bgcolor: 'action.hover',
            color: 'text.primary',
            overflowX: 'auto',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            fontSize: '0.8rem',
            fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
          }}
        >
          {command}
        </Box>
        <Tooltip title={t('managedAgents.installCommand.copy')}>
          <Button
            aria-label={t('managedAgents.installCommand.copy')}
            variant="outlined"
            size="small"
            onClick={() => onCopy(command)}
            sx={{
              position: 'absolute',
              top: 8,
              right: 8,
              minWidth: 0,
              width: 32,
              height: 32,
              p: 0,
              color: 'primary.main',
              borderColor: (theme) => alpha(theme.palette.primary.main, 0.45),
              bgcolor: (theme) => alpha(theme.palette.primary.main, 0.08),
              '&:hover': {
                borderColor: 'primary.main',
                bgcolor: (theme) => alpha(theme.palette.primary.main, 0.14),
              },
              '&:focus-visible': {
                outline: '2px solid',
                outlineColor: 'primary.main',
                outlineOffset: 2,
              },
            }}
          >
            <Copy size={15} />
          </Button>
        </Tooltip>
      </Box>
      <Typography
        variant="body2"
        sx={{
          color: 'text.secondary',
        }}
      >
        {t('managedAgents.installCommand.description')}
      </Typography>
      <Box
        sx={{
          mt: 0.5,
          p: 1.5,
          borderRadius: 1,
          border: '1px solid',
          borderColor: connectedAgent ? 'success.main' : 'divider',
          bgcolor: (theme) =>
            connectedAgent
              ? alpha(theme.palette.success.main, 0.08)
              : alpha(theme.palette.primary.main, 0.04),
          display: 'flex',
          alignItems: 'center',
          gap: 1.5,
        }}
      >
        {connectedAgent ? (
          <CheckCircle size={20} style={{ flexShrink: 0, color: 'currentColor' }} />
        ) : (
          <Box
            sx={{
              flexShrink: 0,
              width: 20,
              height: 20,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              animation: `${spin} 1.2s linear infinite`,
              '@media (prefers-reduced-motion: reduce)': { animation: 'none' },
              color: 'primary.main',
            }}
          >
            <Loader2 size={18} />
          </Box>
        )}
        <Stack spacing={0.25} sx={{ minWidth: 0 }}>
          <Typography
            variant="body2"
            sx={{
              fontWeight: 600,
            }}
          >
            {connectedAgent
              ? t('managedAgents.installCommand.connected', {
                  name: connectedAgent.name || connectedAgent.hostname || t('managedAgents.agent'),
                })
              : t('managedAgents.installCommand.waiting')}
          </Typography>
          <Typography
            variant="caption"
            sx={{
              color: 'text.secondary',
            }}
          >
            {connectedAgent
              ? t('managedAgents.installCommand.connectedDescription')
              : t('managedAgents.installCommand.waitingDescription')}
          </Typography>
        </Stack>
      </Box>
    </Stack>
  )
}
