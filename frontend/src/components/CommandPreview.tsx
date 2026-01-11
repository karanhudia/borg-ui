import { Box, Typography, Alert } from '@mui/material'
import { generateBorgCreateCommand } from '../utils/borgUtils'

interface CommandPreviewProps {
  mode: 'create' | 'import'
  repositoryPath: string
  repositoryType?: 'local' | 'ssh' | 'sftp'
  host?: string
  username?: string
  port?: number
  encryption?: string
  compression?: string
  excludePatterns?: string[]
  sourceDirs?: string[]
  customFlags?: string
  remotePath?: string
  repositoryMode?: 'full' | 'observe'
}

export default function CommandPreview({
  mode,
  repositoryPath,
  repositoryType = 'local',
  host,
  username,
  port = 22,
  encryption = 'repokey',
  compression = 'lz4',
  excludePatterns = [],
  sourceDirs = [],
  customFlags = '',
  remotePath = '',
  repositoryMode = 'full',
}: CommandPreviewProps) {
  // Build full repository path
  let fullRepoPath = repositoryPath || '/path/to/repository'
  if (repositoryType === 'ssh' && host && username) {
    fullRepoPath = `ssh://${username}@${host}:${port}${repositoryPath.startsWith('/') ? '' : '/'}${repositoryPath}`
  }

  const remotePathFlag = remotePath ? `--remote-path ${remotePath} ` : ''

  // Generate init command
  const initCommand = `borg init --encryption ${encryption} ${remotePathFlag}${fullRepoPath}`

  // Generate create command
  const createCommand = generateBorgCreateCommand({
    repositoryPath: fullRepoPath,
    compression,
    excludePatterns,
    sourceDirs: sourceDirs.length > 0 ? sourceDirs : ['/path/to/source'],
    customFlags,
    remotePathFlag,
  })

  return (
    <Alert severity="info" sx={{ mb: 2 }}>
      <Typography variant="subtitle2" gutterBottom>
        {mode === 'create' ? 'Commands that will run:' : 'Backup Command Preview:'}
      </Typography>

      {mode === 'create' && (
        <>
          <Typography variant="caption" display="block" sx={{ mb: 0.5, fontWeight: 600 }}>
            1. Initialize Repository:
          </Typography>
          <Box
            sx={{
              bgcolor: 'grey.900',
              color: 'grey.100',
              p: 1.5,
              borderRadius: 1,
              fontFamily: 'monospace',
              fontSize: '0.875rem',
              overflow: 'auto',
              mb: 2,
            }}
          >
            {initCommand}
          </Box>
        </>
      )}

      {repositoryMode === 'full' && (
        <>
          <Typography variant="caption" display="block" sx={{ mb: 0.5, fontWeight: 600 }}>
            {mode === 'create' ? '2. Create Backup:' : 'Backup Command:'}
          </Typography>
          <Box
            sx={{
              bgcolor: 'grey.900',
              color: 'grey.100',
              p: 1.5,
              borderRadius: 1,
              fontFamily: 'monospace',
              fontSize: '0.875rem',
              overflow: 'auto',
            }}
          >
            {createCommand}
          </Box>
        </>
      )}

      {mode === 'import' && (
        <Typography variant="body2" sx={{ mt: 1.5 }}>
          This command will be used for future backups. The repository will be verified before
          import.
        </Typography>
      )}
    </Alert>
  )
}
