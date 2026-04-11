import { Box, Typography, Tooltip, useTheme, alpha } from '@mui/material'
import { Server, Cloud, HardDrive, Laptop, ArrowRight, MoveRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface SSHConnection {
  id: number
  host: string
  username: string
  port: number
}

interface BackupFlowPreviewProps {
  repositoryLocation: 'local' | 'ssh'
  dataSource: 'local' | 'remote'
  repositoryPath: string
  sourceDirs: string[]
  repoSshConnection?: SSHConnection | null
  sourceSshConnection?: SSHConnection | null
}

const BLUE = '#3b82f6'
const EMERALD = '#10b981'
const AMBER = '#f59e0b'

// Compact horizontal node card: [icon badge] label / subtitle
function FlowNode({
  icon,
  label,
  subtitle,
  accentColor,
  path,
}: {
  icon: React.ReactNode
  label: string
  subtitle?: string
  accentColor: string
  path?: string
}) {
  const theme = useTheme()
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        flex: 1,
        minWidth: 0,
        overflow: 'hidden',
        borderRadius: 1.5,
        bgcolor: alpha(accentColor, theme.palette.mode === 'dark' ? 0.1 : 0.07),
        px: 1.25,
        py: 1,
      }}
    >
      {/* Icon badge */}
      <Box
        sx={{
          width: 32,
          height: 32,
          borderRadius: '9px',
          bgcolor: alpha(accentColor, 0.18),
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: accentColor,
          flexShrink: 0,
        }}
      >
        {icon}
      </Box>

      {/* Text */}
      <Box sx={{ minWidth: 0, overflow: 'hidden' }}>
        <Tooltip title={label} placement="top" disableHoverListener={label.length < 16}>
          <Typography
            variant="body2"
            fontWeight={600}
            fontSize="0.78rem"
            noWrap
            sx={{ color: 'text.primary' }}
          >
            {label}
          </Typography>
        </Tooltip>
        {subtitle && (
          <Typography
            variant="caption"
            color="text.secondary"
            fontSize="0.68rem"
            display="block"
            noWrap
          >
            {subtitle}
          </Typography>
        )}
        {path && (
          <Tooltip title={path} placement="bottom">
            <Typography
              variant="caption"
              fontFamily="monospace"
              fontSize="0.65rem"
              noWrap
              display="block"
              sx={{
                color: accentColor,
                opacity: 0.85,
                cursor: 'default',
                mt: 0.15,
              }}
            >
              {path}
            </Typography>
          </Tooltip>
        )}
      </Box>
    </Box>
  )
}

// Dashed connector between nodes
function Connector({ double = false }: { double?: boolean }) {
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        flexShrink: 0,
        gap: 0.25,
        px: 0.5,
      }}
    >
      <Box
        sx={{
          width: 20,
          borderTop: `2px dashed ${alpha(BLUE, 0.4)}`,
        }}
      />
      {double ? (
        <Box sx={{ display: 'flex', color: alpha(BLUE, 0.7) }}>
          <ArrowRight size={13} />
          <ArrowRight size={13} style={{ marginLeft: -6 }} />
        </Box>
      ) : (
        <MoveRight size={14} color={alpha(BLUE, 0.75)} />
      )}
      <Box
        sx={{
          width: 20,
          borderTop: `2px dashed ${alpha(BLUE, 0.4)}`,
        }}
      />
    </Box>
  )
}

export default function BackupFlowPreview({
  repositoryLocation,
  dataSource,
  repositoryPath,
  sourceDirs,
  repoSshConnection,
  sourceSshConnection,
}: BackupFlowPreviewProps) {
  const { t } = useTranslation()
  const theme = useTheme()

  const getSummaryText = () => {
    if (dataSource === 'local' && repositoryLocation === 'local')
      return t('wizard.backupFlowPreview.localToLocal')
    if (dataSource === 'local' && repositoryLocation === 'ssh')
      return t('wizard.backupFlowPreview.localToRemote')
    if (dataSource === 'remote' && repositoryLocation === 'local')
      return t('wizard.backupFlowPreview.remoteToLocal')
    return t('wizard.backupFlowPreview.default')
  }

  const getSourceLabel = () => {
    if (dataSource === 'local') return t('wizard.borgUiServer')
    if (sourceSshConnection) return `${sourceSshConnection.username}@${sourceSshConnection.host}`
    return t('wizard.remoteClient')
  }

  const getRepoLabel = () => {
    if (repositoryLocation === 'local') return t('wizard.borgUiServer')
    if (repoSshConnection) return `${repoSshConnection.username}@${repoSshConnection.host}`
    return t('wizard.backupFlowPreview.remoteStorage')
  }

  const getSourceIcon = () =>
    dataSource === 'local' ? <HardDrive size={16} /> : <Laptop size={16} />

  const getRepoIcon = () =>
    repositoryLocation === 'local' ? <Server size={16} /> : <Cloud size={16} />

  const showSshfsIntermediate = dataSource === 'remote' && repositoryLocation === 'local'

  const sourceSubtitle =
    sourceDirs.length > 0
      ? t('wizard.backupFlowPreview.dirs', { count: sourceDirs.length })
      : undefined

  return (
    <Box
      sx={{
        borderRadius: 2,
        bgcolor: alpha(BLUE, theme.palette.mode === 'dark' ? 0.06 : 0.04),
        p: 1.5,
        display: 'flex',
        flexDirection: 'column',
        gap: 1.25,
        overflow: 'hidden',
      }}
    >
      {/* Summary header */}
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, flexWrap: 'wrap' }}>
        <Typography
          variant="caption"
          sx={{
            color: 'text.disabled',
            fontWeight: 700,
            fontSize: '0.6rem',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            flexShrink: 0,
          }}
        >
          Backup Flow
        </Typography>
        <Typography variant="caption" fontWeight={500} fontSize="0.72rem" sx={{ color: BLUE }}>
          {getSummaryText()}
        </Typography>
      </Box>

      {/* Pipeline row */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 0.5,
          minWidth: 0,
        }}
      >
        {/* Source */}
        <FlowNode
          icon={getSourceIcon()}
          label={getSourceLabel()}
          subtitle={sourceSubtitle}
          accentColor={BLUE}
        />

        <Connector double={showSshfsIntermediate} />

        {/* Intermediate SSHFS node */}
        {showSshfsIntermediate && (
          <>
            <FlowNode
              icon={<Server size={16} />}
              label={t('wizard.backupFlowPreview.viaSSHFS')}
              accentColor={AMBER}
            />
            <Connector />
          </>
        )}

        {/* Repository */}
        <FlowNode
          icon={getRepoIcon()}
          label={getRepoLabel()}
          accentColor={EMERALD}
          path={repositoryPath || undefined}
        />
      </Box>
    </Box>
  )
}
