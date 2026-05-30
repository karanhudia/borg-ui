import { Box, Button, Chip, Stack, Tooltip, Typography } from '@mui/material'
import { alpha, keyframes } from '@mui/material/styles'
import { CheckCircle, Copy, Loader2 } from 'lucide-react'
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

const pulseDot = keyframes`
  0%, 100% { opacity: 0.35; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1); }
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
  const command = buildAgentInstallCommand(
    serverUrl,
    token,
    agentName,
    borgInstallMode,
    serviceUserMode
  )

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle2" fontWeight={700}>
          Install command
        </Typography>
        <Chip
          size="small"
          icon={
            connectedAgent ? (
              <CheckCircle size={14} />
            ) : (
              <Box
                component="span"
                sx={{
                  display: 'inline-flex',
                  animation: `${spin} 1s linear infinite`,
                  '@media (prefers-reduced-motion: reduce)': { animation: 'none' },
                }}
              >
                <Loader2 size={14} />
              </Box>
            )
          }
          color={connectedAgent ? 'success' : 'default'}
          label={connectedAgent ? 'Connected' : 'Waiting…'}
          variant={connectedAgent ? 'filled' : 'outlined'}
        />
      </Stack>
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
        <Tooltip title="Copy install command">
          <Button
            aria-label="Copy install command"
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
      <Typography variant="body2" color="text.secondary">
        Run the command on the Linux machine. The installer registers the agent and enables the
        systemd service by default.
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
          <Typography variant="body2" fontWeight={600}>
            {connectedAgent
              ? `${connectedAgent.name || connectedAgent.hostname || 'Agent'} connected`
              : 'Waiting for agent to connect…'}
          </Typography>
          <Stack direction="row" spacing={0.5} alignItems="center" sx={{ color: 'text.secondary' }}>
            {!connectedAgent && (
              <Box
                aria-hidden
                sx={{
                  display: 'inline-flex',
                  gap: 0.4,
                  '& > span': {
                    width: 4,
                    height: 4,
                    borderRadius: '50%',
                    bgcolor: 'primary.main',
                    animation: `${pulseDot} 1.2s ease-in-out infinite`,
                    '@media (prefers-reduced-motion: reduce)': { animation: 'none' },
                  },
                  '& > span:nth-of-type(2)': { animationDelay: '0.2s' },
                  '& > span:nth-of-type(3)': { animationDelay: '0.4s' },
                }}
              >
                <span />
                <span />
                <span />
              </Box>
            )}
            <Typography variant="caption">
              {connectedAgent
                ? 'You can close this dialog — the agent will keep running.'
                : 'This page will update automatically once the install completes.'}
            </Typography>
          </Stack>
        </Stack>
      </Box>
    </Stack>
  )
}
