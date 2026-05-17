import { useEffect, useRef, useState } from 'react'
import { Box, Typography, Paper, IconButton, Tooltip } from '@mui/material'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import CheckIcon from '@mui/icons-material/Check'
import { generateBorgCreateCommand, generateBorgInitCommand } from '../utils/borgUtils'
import { useTranslation } from 'react-i18next'
import { toast } from 'react-hot-toast'

interface SourceSshConnection {
  username: string
  host: string
  port: number
  defaultPath?: string
}

interface CommandPreviewProps {
  mode: 'create' | 'import'
  displayMode?: 'detailed' | 'backup-only'
  repositoryPath: string
  borgVersion?: 1 | 2
  archiveName?: string
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

interface CopyableCommandBoxProps {
  command: string
}

const CopyableCommandBox = ({ command }: CopyableCommandBoxProps) => {
  const [copied, setCopied] = useState(false)
  const resetCopiedTimeoutRef = useRef<number | null>(null)
  const { t } = useTranslation()

  useEffect(() => {
    return () => {
      if (resetCopiedTimeoutRef.current !== null) {
        window.clearTimeout(resetCopiedTimeoutRef.current)
      }
    }
  }, [])

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(command)
      setCopied(true)
      toast.success(t('commandPreview.commandCopied'))
      if (resetCopiedTimeoutRef.current !== null) {
        window.clearTimeout(resetCopiedTimeoutRef.current)
      }
      resetCopiedTimeoutRef.current = window.setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error(t('commandPreview.copyFailed'))
    }
  }

  const copyLabel = copied ? t('commandPreview.copied') : t('commandPreview.copyToClipboard')

  return (
    <Box
      sx={{
        position: 'relative',
        bgcolor: 'grey.900',
        color: 'grey.100',
        p: 1.5,
        pr: 5,
        borderRadius: 1,
        fontFamily: 'monospace',
        fontSize: '0.8rem',
        overflow: 'auto',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
      }}
    >
      {command}
      <Tooltip title={copyLabel}>
        <IconButton
          size="small"
          aria-label={copyLabel}
          onClick={handleCopy}
          sx={{
            position: 'absolute',
            top: 4,
            right: 4,
            color: 'grey.400',
            bgcolor: 'rgba(255,255,255,0.08)',
            '&:hover': {
              bgcolor: 'rgba(255,255,255,0.16)',
              color: 'grey.200',
            },
          }}
        >
          {copied ? <CheckIcon fontSize="small" /> : <ContentCopyIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
    </Box>
  )
}

export default function CommandPreview({
  mode,
  displayMode = 'detailed',
  repositoryPath,
  borgVersion = 1,
  archiveName,
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
  const { t } = useTranslation()
  const isRemoteSource = dataSource === 'remote' && sourceSshConnection

  // Build full repository path
  let fullRepoPath = repositoryPath || '/path/to/repository'
  if (repositoryLocation === 'ssh' && host && username) {
    fullRepoPath = `ssh://${username}@${host}:${port}${repositoryPath.startsWith('/') ? '' : '/'}${repositoryPath}`
  }

  const remotePathFlag = remotePath ? `--remote-path ${remotePath} ` : ''

  // Generate init command
  const initCommand = generateBorgInitCommand({
    repositoryPath: fullRepoPath,
    borgVersion,
    encryption,
    remotePathFlag,
  })

  // For remote source, show the preserved path structure (strips leading slash)
  // Example: /var/snap/docker/.../portainer/_data -> var/snap/docker/.../portainer/_data
  const getPreservedRemotePath = (path: string) => {
    return path.startsWith('/') ? path.substring(1) : path
  }

  const resolveRemoteSourcePath = (path: string) => {
    const rawPath = (path || '').trim()
    const defaultPath = sourceSshConnection?.defaultPath?.trim() || '/'
    const normalizedDefaultPath = defaultPath.startsWith('/') ? defaultPath : `/${defaultPath}`

    let resolvedPath = normalizedDefaultPath
    if (!rawPath || rawPath === '.' || rawPath === './') {
      resolvedPath = normalizedDefaultPath
    } else if (rawPath.startsWith('/')) {
      resolvedPath = rawPath
    } else {
      resolvedPath = `${normalizedDefaultPath.replace(/\/$/, '')}/${rawPath}`
    }

    return resolvedPath.replace(/\/\/+/g, '/')
  }

  const resolvedRemoteSourceDirs = isRemoteSource
    ? sourceDirs.map(resolveRemoteSourcePath)
    : sourceDirs
  const effectiveSourceDirs = isRemoteSource
    ? resolvedRemoteSourceDirs.map(getPreservedRemotePath)
    : sourceDirs.length > 0
      ? sourceDirs
      : ['/path/to/source']

  // Generate create command
  // Note: Exclude patterns now work for remote sources since paths are preserved
  const createCommand = generateBorgCreateCommand({
    repositoryPath: fullRepoPath,
    borgVersion,
    archiveName,
    compression,
    excludePatterns: excludePatterns,
    sourceDirs: effectiveSourceDirs,
    customFlags,
    remotePathFlag,
  })

  if (displayMode === 'backup-only') {
    return (
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Typography variant="subtitle2" gutterBottom sx={{ mb: 1.5 }}>
          {t('backup.commandPreview')}
        </Typography>
        <CopyableCommandBox command={createCommand} />
      </Paper>
    )
  }

  // For remote source backup flow
  if (isRemoteSource && repositoryMode === 'full') {
    // Determine unique parent directories that will be mounted
    // Note: SSHFS can only mount directories, not files
    // For files like /home/user/file.txt, we mount /home/user/
    // Multiple files in the same parent share one mount (deduplication)

    const getParentOrSelf = (path: string): string => {
      // Heuristic: if path has an extension, it's likely a file -> use parent
      // Otherwise, treat as directory
      const hasExtension = path.includes('.') && !path.endsWith('/')
      if (hasExtension) {
        // File: return parent directory
        const lastSlash = path.lastIndexOf('/')
        return lastSlash > 0 ? path.substring(0, lastSlash) : '/'
      }
      // Directory: return as-is
      return path
    }

    const mountPaths =
      resolvedRemoteSourceDirs.length > 0
        ? [...new Set(resolvedRemoteSourceDirs.map(getParentOrSelf))] // Deduplicate
        : ['/path']

    const sshfsMountCommands = mountPaths.map(
      (dir) =>
        `sshfs ${sourceSshConnection.username}@${sourceSshConnection.host}:${dir} /tmp/sshfs_mount_123/${getPreservedRemotePath(dir)} -p ${sourceSshConnection.port}`
    )

    const mountDisplayText =
      mountPaths.length === 1
        ? t('commandPreview.mountDisplayText')
        : t('commandPreview.mountDisplayTextMultiple', { count: mountPaths.length })

    return (
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Typography variant="subtitle2" gutterBottom sx={{ mb: 2 }}>
          {mode === 'create'
            ? t('commandPreview.howBackupWillWork')
            : t('commandPreview.howBackupWorks')}
        </Typography>

        {mode === 'create' && (
          <Box sx={{ mb: 2 }}>
            <Typography
              variant="caption"
              color="primary.main"
              fontWeight={600}
              sx={{ mb: 0.5, display: 'block' }}
            >
              {t('commandPreview.step1InitRepo')}
            </Typography>
            <CopyableCommandBox command={initCommand} />
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
              ? t('commandPreview.step2MountRemote', {
                  type:
                    mountPaths.length > 1
                      ? t('commandPreview.mountDirectories')
                      : t('commandPreview.mountDirectory'),
                })
              : t('commandPreview.step1MountRemote', {
                  type:
                    mountPaths.length > 1
                      ? t('commandPreview.mountDirectories')
                      : t('commandPreview.mountDirectory'),
                })}
          </Typography>
          <CopyableCommandBox command={sshfsMountCommands.join('\n')} />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
            {mountDisplayText}
          </Typography>
        </Box>

        <Box sx={{ mb: 2 }}>
          <Typography
            variant="caption"
            color="primary.main"
            fontWeight={600}
            sx={{ mb: 0.5, display: 'block' }}
          >
            {mode === 'create'
              ? t('commandPreview.step3RunBackup')
              : t('commandPreview.step2RunBackup')}
          </Typography>
          <CopyableCommandBox command={createCommand} />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
            {t('commandPreview.archivesPreserve')}
          </Typography>
        </Box>

        <Box>
          <Typography
            variant="caption"
            color="primary.main"
            fontWeight={600}
            sx={{ mb: 0.5, display: 'block' }}
          >
            {mode === 'create'
              ? t('commandPreview.step4Cleanup')
              : t('commandPreview.step3Cleanup')}
          </Typography>
          <CopyableCommandBox command="fusermount -u /tmp/sshfs_mount/" />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
            {t('commandPreview.cleanupDesc')}
          </Typography>
        </Box>
      </Paper>
    )
  }

  // Standard local source flow
  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
      <Typography variant="subtitle2" gutterBottom sx={{ mb: 2 }}>
        {mode === 'create'
          ? t('commandPreview.howBackupWillWork')
          : t('commandPreview.howBackupWorks')}
      </Typography>

      {mode === 'create' && (
        <Box sx={{ mb: 2 }}>
          <Typography
            variant="caption"
            color="primary.main"
            fontWeight={600}
            sx={{ mb: 0.5, display: 'block' }}
          >
            {t('commandPreview.step1InitRepo')}
          </Typography>
          <CopyableCommandBox command={initCommand} />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
            {t('commandPreview.initRepositoryDesc')}
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
            {mode === 'create'
              ? t('commandPreview.step2RunBackup')
              : t('commandPreview.stepRunBackup')}
          </Typography>
          <CopyableCommandBox command={createCommand} />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
            {mode === 'create'
              ? t('commandPreview.backupSourceDirs')
              : t('commandPreview.futureBackups')}
          </Typography>
        </Box>
      )}
    </Paper>
  )
}
