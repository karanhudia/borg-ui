import React, { useState } from 'react'
import { Box, Typography, Alert, Paper, Chip, Divider, IconButton, Tooltip } from '@mui/material'
import {
  FolderOpen,
  Shield,
  Settings,
  Server,
  Cloud,
  HardDrive,
  Laptop,
  Info,
  Eye,
  EyeOff,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
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
  borgVersion?: 1 | 2
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
}

interface WizardStepReviewProps {
  mode: 'create' | 'edit' | 'import'
  data: WizardReviewData
  sshConnections: SSHConnection[]
}

// SummaryRow component defined outside render to avoid re-creation
function SummaryRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: { xs: 'column', sm: 'row' },
        justifyContent: 'space-between',
        alignItems: { xs: 'flex-start', sm: 'center' },
        gap: 0.5,
        py: 0.75,
      }}
    >
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Box sx={{ textAlign: { xs: 'left', sm: 'right' }, width: { xs: '100%', sm: 'auto' } }}>
        {children}
      </Box>
    </Box>
  )
}

function getEncryptionLabelKey(encryption: string) {
  if (encryption === 'none') {
    return 'wizard.review.encryptionNone'
  }

  if (encryption.startsWith('repokey')) {
    return 'wizard.review.encryptionRepokey'
  }

  if (encryption.startsWith('keyfile')) {
    return 'wizard.review.encryptionKeyfile'
  }

  return 'wizard.review.encryptionNone'
}

export default function WizardStepReview({ mode, data, sshConnections }: WizardStepReviewProps) {
  const { t } = useTranslation()
  const [showPassphrase, setShowPassphrase] = useState(false)

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
    return {
      host: '',
      username: '',
      port: 22,
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
            borgVersion={data.borgVersion}
            repositoryPath={data.path}
            repositoryLocation={data.repositoryLocation}
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
            {t('wizard.review.configurationSummary')}
          </Typography>
        </Box>

        {/* Repository Info */}
        <Box sx={{ px: 2, py: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <FolderOpen size={16} />
            <Typography variant="caption" fontWeight={600} color="text.secondary">
              {t('wizard.review.repository')}
            </Typography>
          </Box>

          <SummaryRow label={t('wizard.review.name')}>
            <Typography variant="body2" fontWeight={600}>
              {data.name}
            </Typography>
          </SummaryRow>

          <SummaryRow label={t('wizard.review.mode')}>
            <Chip
              label={
                data.repositoryMode === 'full'
                  ? t('wizard.review.full')
                  : t('wizard.review.observeOnly')
              }
              size="small"
              color={data.repositoryMode === 'full' ? 'primary' : 'default'}
            />
          </SummaryRow>

          <SummaryRow label={t('wizard.review.location')}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              {data.repositoryLocation === 'local' ? <Server size={14} /> : <Cloud size={14} />}
              <Typography variant="body2" fontWeight={500}>
                {data.repositoryLocation === 'local'
                  ? t('wizard.review.borgUiServer')
                  : t('wizard.review.sshRemote')}
              </Typography>
            </Box>
          </SummaryRow>

          <SummaryRow label={t('wizard.review.path')}>
            <Typography variant="body2" fontFamily="monospace" fontSize="0.8rem">
              {data.path || t('wizard.review.notSet')}
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
                  {t('wizard.review.dataSource')}
                </Typography>
              </Box>

              <SummaryRow label={t('wizard.review.source')}>
                <Typography variant="body2" fontWeight={500}>
                  {data.dataSource === 'local'
                    ? t('wizard.review.borgUiServer')
                    : t('wizard.review.remoteClient')}
                </Typography>
              </SummaryRow>

              {data.dataSource === 'local' && (
                <>
                  <SummaryRow label={t('wizard.review.directories')}>
                    <Typography variant="body2">
                      {t('wizard.review.directoriesCount', { count: data.sourceDirs.length })}
                    </Typography>
                  </SummaryRow>

                  <SummaryRow label={t('wizard.review.excludePatterns')}>
                    <Typography variant="body2">
                      {t('wizard.review.directoriesCount', { count: data.excludePatterns.length })}
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
              {t('wizard.review.security')}
            </Typography>
          </Box>

          {mode === 'create' && (
            <SummaryRow label={t('wizard.review.encryption')}>
              <Chip
                label={t(getEncryptionLabelKey(data.encryption))}
                size="small"
                color={data.encryption === 'none' ? 'error' : 'success'}
              />
            </SummaryRow>
          )}

          <SummaryRow label={t('wizard.review.passphrase')}>
            {data.passphrase ? (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Typography variant="body2" fontFamily={showPassphrase ? 'inherit' : 'monospace'}>
                  {showPassphrase ? data.passphrase : '••••••••'}
                </Typography>
                <Tooltip title={showPassphrase ? 'Hide passphrase' : 'Show passphrase'}>
                  <IconButton
                    aria-label={showPassphrase ? 'Hide passphrase' : 'Show passphrase'}
                    onClick={() => setShowPassphrase((v) => !v)}
                    size="small"
                    sx={{ p: 0.25 }}
                  >
                    {showPassphrase ? <EyeOff size={14} /> : <Eye size={14} />}
                  </IconButton>
                </Tooltip>
              </Box>
            ) : (
              <Typography variant="body2">{t('wizard.review.passphraseNotSet')}</Typography>
            )}
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
                  {t('wizard.review.backupConfiguration')}
                </Typography>
              </Box>

              <SummaryRow label={t('wizard.review.compression')}>
                <Typography variant="body2" fontFamily="monospace" fontSize="0.8rem">
                  {data.compression}
                </Typography>
              </SummaryRow>

              {data.customFlags && (
                <SummaryRow label={t('wizard.review.customFlags')}>
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
          <Typography variant="body2">{t('wizard.review.repositoryInitialized')}</Typography>
        </Alert>
      )}

      {mode === 'import' && (
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.75 }}>
          <Info size={14} style={{ opacity: 0.45, flexShrink: 0, marginTop: 2 }} />
          <Typography variant="body2" color="text.secondary">
            {t('wizard.review.repositoryImportNote')}
          </Typography>
        </Box>
      )}

      {mode === 'edit' && (
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.75 }}>
          <Info size={14} style={{ opacity: 0.45, flexShrink: 0, marginTop: 2 }} />
          <Typography variant="body2" color="text.secondary">
            {t('wizard.review.repositoryEditNote')}
          </Typography>
        </Box>
      )}
    </Box>
  )
}
