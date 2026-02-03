import React from 'react'
import { Box, Typography, Paper } from '@mui/material'
import { generateBorgCreateCommand } from '../utils/borgUtils'

interface SourceSshConnection {
  username: string
  host: string
  port: number
}

interface CommandPreviewProps {
  mode: 'create' | 'import'
  repositoryPath: string
  repositoryLocation?: 'local' | 'ssh'
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
  // Remote source props
  dataSource?: 'local' | 'remote'
  sourceSshConnection?: SourceSshConnection | null
}

const CommandBox = ({ children }: { children: React.ReactNode }) => (
  <Box
    sx={{
      bgcolor: 'grey.900',
      color: 'grey.100',
      p: 1.5,
      borderRadius: 1,
      fontFamily: 'monospace',
      fontSize: '0.8rem',
      overflow: 'auto',
      whiteSpace: 'pre-wrap',
      wordBreak: 'break-all',
    }}
  >
    {children}
  </Box>
)

export default function CommandPreview({
  mode,
  repositoryPath,
  repositoryLocation = 'local',
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
  dataSource = 'local',
  sourceSshConnection = null,
}: CommandPreviewProps) {
  const isRemoteSource = dataSource === 'remote' && sourceSshConnection

  // Build full repository path
  let fullRepoPath = repositoryPath || '/path/to/repository'
  if (repositoryLocation === 'ssh' && host && username) {
    fullRepoPath = `ssh://${username}@${host}:${port}${repositoryPath.startsWith('/') ? '' : '/'}${repositoryPath}`
  }

  const remotePathFlag = remotePath ? `--remote-path ${remotePath} ` : ''

  // Generate init command
  const initCommand = `borg init --encryption ${encryption} ${remotePathFlag}${fullRepoPath}`

  // For remote source, show the preserved path structure (strips leading slash)
  // Example: /var/snap/docker/.../portainer/_data -> var/snap/docker/.../portainer/_data
  const getPreservedRemotePath = (path: string) => {
    return path.startsWith('/') ? path.substring(1) : path
  }

  const effectiveSourceDirs = isRemoteSource
    ? sourceDirs.map(getPreservedRemotePath)
    : sourceDirs.length > 0
      ? sourceDirs
      : ['/path/to/source']

  // Generate create command
  // Note: Exclude patterns now work for remote sources since paths are preserved
  const createCommand = generateBorgCreateCommand({
    repositoryPath: fullRepoPath,
    compression,
    excludePatterns: excludePatterns,
    sourceDirs: effectiveSourceDirs,
    customFlags,
    remotePathFlag,
  })

  // For remote source backup flow
  if (isRemoteSource && repositoryMode === 'full') {
    const sshfsMount = `sshfs ${sourceSshConnection.username}@${sourceSshConnection.host}:${sourceDirs[0] || '/path'} /tmp/sshfs_mount/ -p ${sourceSshConnection.port}`

    return (
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Typography variant="subtitle2" gutterBottom sx={{ mb: 2 }}>
          {mode === 'create' ? 'How backup will work:' : 'How backup works:'}
        </Typography>

        {mode === 'create' && (
          <Box sx={{ mb: 2 }}>
            <Typography
              variant="caption"
              color="primary.main"
              fontWeight={600}
              sx={{ mb: 0.5, display: 'block' }}
            >
              Step 1: Initialize Repository
            </Typography>
            <CommandBox>{initCommand}</CommandBox>
          </Box>
        )}

        <Box sx={{ mb: 2 }}>
          <Typography
            variant="caption"
            color="primary.main"
            fontWeight={600}
            sx={{ mb: 0.5, display: 'block' }}
          >
            {mode === 'create'
              ? 'Step 2: Mount Remote Directory'
              : 'Step 1: Mount Remote Directory'}
          </Typography>
          <CommandBox>{sshfsMount}</CommandBox>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
            Temporarily mounts remote directory via SSHFS (preserves full path structure)
          </Typography>
        </Box>

        <Box sx={{ mb: 2 }}>
          <Typography
            variant="caption"
            color="primary.main"
            fontWeight={600}
            sx={{ mb: 0.5, display: 'block' }}
          >
            {mode === 'create' ? 'Step 3: Run Backup' : 'Step 2: Run Backup'}
          </Typography>
          <CommandBox>{createCommand}</CommandBox>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
            Archives preserve original paths (excludes work intuitively)
          </Typography>
        </Box>

        <Box>
          <Typography
            variant="caption"
            color="primary.main"
            fontWeight={600}
            sx={{ mb: 0.5, display: 'block' }}
          >
            {mode === 'create' ? 'Step 4: Cleanup' : 'Step 3: Cleanup'}
          </Typography>
          <CommandBox>fusermount -u /tmp/sshfs_mount/</CommandBox>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
            Unmounts remote directory after backup completes
          </Typography>
        </Box>
      </Paper>
    )
  }

  // Standard local source flow
  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
      <Typography variant="subtitle2" gutterBottom sx={{ mb: 2 }}>
        {mode === 'create' ? 'How backup will work:' : 'How backup works:'}
      </Typography>

      {mode === 'create' && (
        <Box sx={{ mb: 2 }}>
          <Typography
            variant="caption"
            color="primary.main"
            fontWeight={600}
            sx={{ mb: 0.5, display: 'block' }}
          >
            Step 1: Initialize Repository
          </Typography>
          <CommandBox>{initCommand}</CommandBox>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
            Creates encrypted repository at the specified location
          </Typography>
        </Box>
      )}

      {repositoryMode === 'full' && (
        <Box>
          <Typography
            variant="caption"
            color="primary.main"
            fontWeight={600}
            sx={{ mb: 0.5, display: 'block' }}
          >
            {mode === 'create' ? 'Step 2: Run Backup' : 'Run Backup'}
          </Typography>
          <CommandBox>{createCommand}</CommandBox>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
            {mode === 'create'
              ? 'Backs up source directories to the repository'
              : 'This command will be used for future backups'}
          </Typography>
        </Box>
      )}
    </Paper>
  )
}
