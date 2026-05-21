import { Box, Button, Chip, Stack, Tooltip, Typography } from '@mui/material'
import { CheckCircle, Copy, Loader2 } from 'lucide-react'
import type { AgentMachineResponse } from '../../services/api'
import { buildAgentInstallCommand } from './agentInstallCommandText'

export default function AgentInstallCommand({
  serverUrl,
  token,
  agentName,
  connectedAgent,
  onCopy,
}: {
  serverUrl: string
  token: string
  agentName: string
  connectedAgent?: AgentMachineResponse | null
  onCopy: (value: string) => void
}) {
  const command = buildAgentInstallCommand(serverUrl, token, agentName)

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle2" fontWeight={700}>
          Install command
        </Typography>
        <Chip
          size="small"
          icon={connectedAgent ? <CheckCircle size={14} /> : <Loader2 size={14} />}
          color={connectedAgent ? 'success' : 'default'}
          label={connectedAgent ? 'Agent connected' : 'Waiting for agent to connect...'}
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
              bgcolor: 'background.paper',
            }}
          >
            <Copy size={15} />
          </Button>
        </Tooltip>
      </Box>
      <Typography variant="body2" color="text.secondary">
        Run the command on the Linux or Raspberry Pi machine. The installer registers the agent and
        enables the systemd service by default.
      </Typography>
    </Stack>
  )
}
