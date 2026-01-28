import { Box, Typography, alpha, Paper } from '@mui/material'
import { Server, Cloud, HardDrive, Laptop, ArrowRight, ArrowRightLeft } from 'lucide-react'

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

export default function BackupFlowPreview({
  repositoryLocation,
  dataSource,
  repositoryPath,
  sourceDirs,
  repoSshConnection,
  sourceSshConnection,
}: BackupFlowPreviewProps) {
  // Generate summary text
  const getSummaryText = () => {
    if (dataSource === 'local' && repositoryLocation === 'local') {
      return 'Back up local data to local repository'
    }
    if (dataSource === 'local' && repositoryLocation === 'ssh') {
      return 'Back up local data to remote repository'
    }
    if (dataSource === 'remote' && repositoryLocation === 'local') {
      return 'Back up remote data to local repository via SSHFS'
    }
    return 'Back up data to repository'
  }

  const getSourceLabel = () => {
    if (dataSource === 'local') {
      return 'Borg UI Server'
    }
    if (sourceSshConnection) {
      return `${sourceSshConnection.username}@${sourceSshConnection.host}`
    }
    return 'Remote Client'
  }

  const getRepoLabel = () => {
    if (repositoryLocation === 'local') {
      return 'Borg UI Server'
    }
    if (repoSshConnection) {
      return `${repoSshConnection.username}@${repoSshConnection.host}`
    }
    return 'Remote Storage'
  }

  const getSourceIcon = () => {
    if (dataSource === 'local') {
      return <HardDrive size={20} />
    }
    return <Laptop size={20} />
  }

  const getRepoIcon = () => {
    if (repositoryLocation === 'local') {
      return <Server size={20} />
    }
    return <Cloud size={20} />
  }

  const showSshfsIntermediate = dataSource === 'remote' && repositoryLocation === 'local'

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        bgcolor: (theme) => alpha(theme.palette.primary.main, 0.04),
        borderColor: (theme) => alpha(theme.palette.primary.main, 0.2),
        borderRadius: 2,
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          mb: 1.5,
        }}
      >
        <Typography variant="body2" color="primary" sx={{ fontSize: '0.8125rem', fontWeight: 500 }}>
          {getSummaryText()}
        </Typography>
        {repositoryPath && (
          <Box
            component="span"
            sx={{
              fontFamily: 'monospace',
              bgcolor: 'background.paper',
              px: 1,
              py: 0.5,
              borderRadius: 1,
              border: 1,
              borderColor: 'divider',
              fontSize: '0.7rem',
              maxWidth: 200,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={repositoryPath}
          >
            {repositoryPath}
          </Box>
        )}
      </Box>

      {/* Visual Flow Diagram */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'center',
          gap: 3,
          py: 2,
          px: 2,
        }}
      >
        {/* Source Node */}
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 1,
            width: 90,
          }}
        >
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 44,
              height: 44,
              borderRadius: 2.5,
              bgcolor: 'background.paper',
              border: 2,
              borderColor: 'primary.main',
              color: 'primary.main',
              boxShadow: '0 4px 12px rgba(0,0,0,0.05)',
            }}
          >
            {getSourceIcon()}
          </Box>
          <Box sx={{ textAlign: 'center' }}>
            <Typography
              variant="subtitle2"
              color="text.primary"
              sx={{
                fontWeight: 600,
                fontSize: '0.8rem',
                lineHeight: 1.2,
              }}
            >
              {getSourceLabel()}
            </Typography>
            {sourceDirs.length > 0 && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ fontSize: '0.7rem', mt: 0.5, display: 'block' }}
              >
                {sourceDirs.length} dir{sourceDirs.length !== 1 ? 's' : ''}
              </Typography>
            )}
          </Box>
        </Box>

        {/* Arrow */}
        <Box sx={{ display: 'flex', alignItems: 'center', color: 'primary.main', pt: 1.5 }}>
          {showSshfsIntermediate ? <ArrowRightLeft size={20} /> : <ArrowRight size={20} />}
        </Box>

        {/* Intermediate Node (SSHFS) - only for remote source to local repo */}
        {showSshfsIntermediate && (
          <>
            <Box
              sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 1,
                width: 80,
              }}
            >
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 36,
                  height: 36,
                  borderRadius: 2,
                  bgcolor: 'action.selected',
                  border: 1,
                  borderColor: 'divider',
                  color: 'text.secondary',
                }}
              >
                <Server size={18} />
              </Box>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ fontSize: '0.7rem', fontWeight: 500 }}
              >
                via SSHFS
              </Typography>
            </Box>

            {/* Arrow to repo */}
            <Box sx={{ display: 'flex', alignItems: 'center', color: 'primary.main', pt: 1.5 }}>
              <ArrowRight size={20} />
            </Box>
          </>
        )}

        {/* Repository Node */}
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 1,
            width: 90,
          }}
        >
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 44,
              height: 44,
              borderRadius: 2.5,
              bgcolor: 'success.main',
              color: 'white',
              boxShadow: '0 4px 12px rgba(46, 125, 50, 0.2)',
            }}
          >
            {getRepoIcon()}
          </Box>
          <Box sx={{ textAlign: 'center' }}>
            <Typography
              variant="subtitle2"
              color="text.primary"
              sx={{
                fontWeight: 600,
                fontSize: '0.8rem',
                lineHeight: 1.2,
              }}
            >
              {getRepoLabel()}
            </Typography>
          </Box>
        </Box>
      </Box>
    </Paper>
  )
}
