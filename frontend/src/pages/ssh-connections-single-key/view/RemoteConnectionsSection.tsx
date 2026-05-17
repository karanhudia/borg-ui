import type { TFunction } from 'i18next'
import type { Theme } from '@mui/material/styles'
import { Box, IconButton, Tooltip, Typography, alpha } from '@mui/material'
import { Info, RefreshCw, Wifi } from 'lucide-react'
import RemoteMachineCard from '../../../components/RemoteMachineCard'
import type { SSHConnection } from '../types'

interface RemoteConnectionsSectionProps {
  t: TFunction
  theme: Theme
  isDark: boolean
  keyExists: boolean | undefined
  connections: SSHConnection[]
  canManageSsh: boolean
  onRefreshConnections: () => void
  onEditConnection: (connection: SSHConnection) => void
  onDeleteConnection: (connection: SSHConnection) => void
  onRefreshStorage: (connectionId: number) => void
  onTestConnection: (connection: SSHConnection) => void
  onDeployKeyToConnection: (connection: SSHConnection) => void
}

export function RemoteConnectionsSection({
  t,
  theme,
  isDark,
  keyExists,
  connections,
  canManageSsh,
  onRefreshConnections,
  onEditConnection,
  onDeleteConnection,
  onRefreshStorage,
  onTestConnection,
  onDeployKeyToConnection,
}: RemoteConnectionsSectionProps) {
  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box>
            <Typography variant="h6" fontWeight={700} sx={{ lineHeight: 1.3 }}>
              {t('sshConnections.remoteConnections.title')}
            </Typography>
            {connections.length > 0 && (
              <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8rem' }}>
                {t('sshConnections.remoteConnections.configured', { count: connections.length })}
              </Typography>
            )}
          </Box>
          {!keyExists && connections.length > 0 && (
            <Tooltip title={t('sshConnections.systemKey.noKey')} arrow placement="right">
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: theme.palette.warning.main,
                  cursor: 'help',
                }}
              >
                <Info size={18} />
              </Box>
            </Tooltip>
          )}
        </Box>
        <Tooltip title={t('sshConnections.remoteConnections.refresh')} arrow>
          <IconButton
            aria-label={t('sshConnections.remoteConnections.refresh')}
            size="small"
            onClick={() => onRefreshConnections()}
            sx={{
              width: 32,
              height: 32,
              borderRadius: 1.5,
              color: 'text.secondary',
              '&:hover': {
                bgcolor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.06),
                color: 'text.primary',
              },
            }}
          >
            <RefreshCw size={16} />
          </IconButton>
        </Tooltip>
      </Box>

      {connections.length === 0 ? (
        <Box
          sx={{
            borderRadius: 2,
            border: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
            bgcolor: isDark ? alpha('#fff', 0.025) : alpha('#000', 0.018),
            px: 3,
            py: 4,
            textAlign: 'center',
          }}
        >
          <Box
            sx={{
              width: 44,
              height: 44,
              borderRadius: 2,
              bgcolor: isDark
                ? alpha(theme.palette.primary.main, 0.12)
                : alpha(theme.palette.primary.main, 0.08),
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: theme.palette.primary.main,
              mx: 'auto',
              mb: 1.5,
            }}
          >
            <Wifi size={22} />
          </Box>
          <Typography variant="body1" fontWeight={600} sx={{ mb: 0.5 }}>
            {t('sshConnections.remoteConnections.emptyTitle')}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.82rem' }}>
            {keyExists
              ? t('sshConnections.remoteConnections.emptyWithKey')
              : t('sshConnections.remoteConnections.emptyWithoutKey')}
          </Typography>
        </Box>
      ) : (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: { xs: 2, sm: 2.5 } }}>
          {connections.map((connection) => (
            <Box
              key={connection.id}
              sx={{
                flex: {
                  xs: '0 0 100%',
                  sm: '0 0 calc(50% - 10px)',
                  md: '0 0 calc(33.333% - 14px)',
                },
                minWidth: 0,
                display: 'flex',
              }}
            >
              <RemoteMachineCard
                machine={connection}
                onEdit={onEditConnection}
                onDelete={onDeleteConnection}
                onRefreshStorage={(machine) => onRefreshStorage(machine.id)}
                onTestConnection={onTestConnection}
                onDeployKey={onDeployKeyToConnection}
                canManageConnections={canManageSsh}
              />
            </Box>
          ))}
        </Box>
      )}
    </Box>
  )
}
