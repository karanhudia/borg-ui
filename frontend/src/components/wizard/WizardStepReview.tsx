import React from 'react'
import { Box, Typography, Alert, Paper, Chip, Divider } from '@mui/material'
import { FolderOpen, Shield, Settings, Server, Cloud, HardDrive, Laptop } from 'lucide-react'
import CommandPreview from '../CommandPreview'
import BackupFlowPreview from './BackupFlowPreview'

interface SSHConnection {
  id: number
  host: string
  username: string
  port: number
  ssh_key_id: number
}

export interface WizardReviewData {
  name: string
  repositoryMode: 'full' | 'observe'
  repositoryLocation: 'local' | 'ssh'
  path: string
  repoSshConnectionId: number | ''
  dataSource: 'local' | 'remote'
  sourceSshConnectionId: number | ''
  sourceDirs: string[]
  encryption: string
  passphrase: string
  compression: string
  excludePatterns: string[]
  customFlags: string
  remotePath: string
  // SSH details for command preview
  host: string
  username: string
  port: number
  repositoryType: 'local' | 'ssh' | 'sftp'
}

interface WizardStepReviewProps {
  mode: 'create' | 'edit' | 'import'
  data: WizardReviewData
  sshConnections: SSHConnection[]
}

// SummaryRow component defined outside render to avoid re-creation
function SummaryRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.75 }}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Box sx={{ textAlign: 'right' }}>{children}</Box>
    </Box>
  )
}

export default function WizardStepReview({ mode, data, sshConnections }: WizardStepReviewProps) {
  // Get source SSH connection details for command preview
  const getSourceSshConnection = () => {
    if (data.dataSource !== 'remote' || !data.sourceSshConnectionId) return null
    const conn = sshConnections.find((c) => c.id === data.sourceSshConnectionId)
    if (!conn) return null
    return {
      username: conn.username,
      host: conn.host,
      port: conn.port,
    }
  }

  // Get repo SSH connection for flow preview
  const getRepoSshConnection = () => {
    if (data.repositoryLocation !== 'ssh' || !data.repoSshConnectionId) return null
    const conn = sshConnections.find((c) => c.id === data.repoSshConnectionId)
    return conn || null
  }

  // Get source SSH connection for flow preview
  const getSourceSshConnectionForFlow = () => {
    if (data.dataSource !== 'remote' || !data.sourceSshConnectionId) return null
    const conn = sshConnections.find((c) => c.id === data.sourceSshConnectionId)
    return conn || null
  }

  // Get repository SSH connection details for command preview
  const getRepoConnectionDetails = () => {
    if (data.repositoryLocation === 'ssh' && data.repoSshConnectionId) {
      const conn = sshConnections.find((c) => c.id === data.repoSshConnectionId)
      if (conn) {
        return {
          host: conn.host,
          username: conn.username,
          port: conn.port,
        }
      }
    }
    // Fallback to wizard state (for backward compatibility or direct input)
    return {
      host: data.host,
      username: data.username,
      port: data.port,
    }
  }

  const repoDetails = getRepoConnectionDetails()

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {/* Backup Flow Preview */}
      {data.repositoryMode === 'full' && (
        <BackupFlowPreview
          repositoryLocation={data.repositoryLocation}
          dataSource={data.dataSource}
          repositoryPath={data.path}
          sourceDirs={data.sourceDirs}
          repoSshConnection={getRepoSshConnection()}
          sourceSshConnection={getSourceSshConnectionForFlow()}
        />
      )}

      {/* Command Preview - Only for full mode with local source */}
      {(data.dataSource === 'local' || data.dataSource === 'remote') &&
        data.repositoryMode === 'full' && (
          <CommandPreview
            mode={mode === 'create' ? 'create' : 'import'}
            repositoryPath={data.path}
            repositoryType={data.repositoryType}
            host={repoDetails.host}
            username={repoDetails.username}
            port={repoDetails.port}
            encryption={data.encryption}
            compression={data.compression}
            excludePatterns={data.excludePatterns}
            sourceDirs={data.sourceDirs}
            customFlags={data.customFlags}
            remotePath={data.remotePath}
            repositoryMode={data.repositoryMode}
            dataSource={data.dataSource}
            sourceSshConnection={getSourceSshConnection()}
          />
        )}

      {/* Summary Cards */}
      <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
        {/* Header */}
        <Box
          sx={{
            px: 2,
            py: 1.5,
            bgcolor: 'background.default',
            borderBottom: 1,
            borderColor: 'divider',
          }}
        >
          <Typography variant="subtitle2" fontWeight={600}>
            Configuration Summary
          </Typography>
        </Box>

        {/* Repository Info */}
        <Box sx={{ px: 2, py: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <FolderOpen size={16} />
            <Typography variant="caption" fontWeight={600} color="text.secondary">
              REPOSITORY
            </Typography>
          </Box>

          <SummaryRow label="Name">
            <Typography variant="body2" fontWeight={600}>
              {data.name}
            </Typography>
          </SummaryRow>

          <SummaryRow label="Mode">
            <Chip
              label={data.repositoryMode === 'full' ? 'Full' : 'Observe Only'}
              size="small"
              color={data.repositoryMode === 'full' ? 'primary' : 'default'}
            />
          </SummaryRow>

          <SummaryRow label="Location">
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              {data.repositoryLocation === 'local' ? <Server size={14} /> : <Cloud size={14} />}
              <Typography variant="body2" fontWeight={500}>
                {data.repositoryLocation === 'local' ? 'Borg UI Server' : 'SSH Remote'}
              </Typography>
            </Box>
          </SummaryRow>

          <SummaryRow label="Path">
            <Typography variant="body2" fontFamily="monospace" fontSize="0.8rem">
              {data.path || '(not set)'}
            </Typography>
          </SummaryRow>
        </Box>

        <Divider />

        {/* Data Source Info - Only for full mode */}
        {data.repositoryMode === 'full' && (
          <>
            <Box sx={{ px: 2, py: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                {data.dataSource === 'local' ? <HardDrive size={16} /> : <Laptop size={16} />}
                <Typography variant="caption" fontWeight={600} color="text.secondary">
                  DATA SOURCE
                </Typography>
              </Box>

              <SummaryRow label="Source">
                <Typography variant="body2" fontWeight={500}>
                  {data.dataSource === 'local' ? 'Borg UI Server' : 'Remote Client'}
                </Typography>
              </SummaryRow>

              {data.dataSource === 'local' && (
                <>
                  <SummaryRow label="Directories">
                    <Typography variant="body2">{data.sourceDirs.length} configured</Typography>
                  </SummaryRow>

                  <SummaryRow label="Exclude Patterns">
                    <Typography variant="body2">
                      {data.excludePatterns.length} configured
                    </Typography>
                  </SummaryRow>
                </>
              )}
            </Box>

            <Divider />
          </>
        )}

        {/* Security Info */}
        <Box sx={{ px: 2, py: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <Shield size={16} />
            <Typography variant="caption" fontWeight={600} color="text.secondary">
              SECURITY
            </Typography>
          </Box>

          {mode === 'create' && (
            <SummaryRow label="Encryption">
              <Chip
                label={
                  data.encryption === 'repokey'
                    ? 'Repokey'
                    : data.encryption === 'keyfile'
                      ? 'Keyfile'
                      : 'None'
                }
                size="small"
                color={data.encryption === 'none' ? 'error' : 'success'}
              />
            </SummaryRow>
          )}

          <SummaryRow label="Passphrase">
            <Typography variant="body2">{data.passphrase ? '••••••••' : '(not set)'}</Typography>
          </SummaryRow>
        </Box>

        {/* Backup Config - Only for full mode */}
        {data.repositoryMode === 'full' && (
          <>
            <Divider />
            <Box sx={{ px: 2, py: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <Settings size={16} />
                <Typography variant="caption" fontWeight={600} color="text.secondary">
                  BACKUP CONFIGURATION
                </Typography>
              </Box>

              <SummaryRow label="Compression">
                <Typography variant="body2" fontFamily="monospace" fontSize="0.8rem">
                  {data.compression}
                </Typography>
              </SummaryRow>

              {data.customFlags && (
                <SummaryRow label="Custom Flags">
                  <Typography variant="body2" fontFamily="monospace" fontSize="0.8rem">
                    {data.customFlags}
                  </Typography>
                </SummaryRow>
              )}
            </Box>
          </>
        )}
      </Paper>

      {/* Action Alerts */}
      {mode === 'create' && data.repositoryMode === 'full' && (
        <Alert severity="success">
          <Typography variant="body2">Repository will be initialized</Typography>
        </Alert>
      )}

      {mode === 'import' && (
        <Alert severity="info">
          <Typography variant="body2">
            Repository will be verified before import. Ensure the passphrase is correct.
          </Typography>
        </Alert>
      )}

      {mode === 'edit' && (
        <Alert severity="info">
          <Typography variant="body2">
            Changes will be saved to the repository configuration.
          </Typography>
        </Alert>
      )}
    </Box>
  )
}
