import { useState } from 'react'
import { Box, Typography, Chip, IconButton, Tooltip, alpha } from '@mui/material'
import {
  FolderOpen,
  Shield,
  Settings,
  Server,
  Cloud,
  HardDrive,
  Laptop,
  Eye,
  EyeOff,
  Lock,
  Unlock,
  Rocket,
  Info,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import CommandPreview from '../CommandPreview'
import BackupFlowPreview from './BackupFlowPreview'
import {
  ReviewAttrRow,
  ReviewCodePill,
  ReviewKicker,
  ReviewSectionCard,
  ReviewSectionGrid,
} from './WizardReviewComponents'

interface SSHConnection {
  id: number
  host: string
  username: string
  port: number
  ssh_key_id: number
  default_path?: string
  ssh_path_prefix?: string
}

interface AgentMachine {
  id: number
  name: string
  hostname?: string | null
  status: string
}

export interface WizardReviewData {
  name: string
  borgVersion?: 1 | 2
  repositoryMode: 'full' | 'observe'
  repositoryLocation: 'local' | 'ssh'
  executionTarget?: 'local' | 'agent'
  agentMachineId?: number | ''
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
  agentMachines?: AgentMachine[]
}

function getEncryptionLabelKey(encryption: string) {
  if (encryption === 'none') return 'wizard.review.encryptionNone'
  if (encryption.startsWith('repokey')) return 'wizard.review.encryptionRepokey'
  if (encryption.startsWith('keyfile')) return 'wizard.review.encryptionKeyfile'
  return 'wizard.review.encryptionNone'
}

export default function WizardStepReview({
  mode,
  data,
  sshConnections,
  agentMachines = [],
}: WizardStepReviewProps) {
  const { t } = useTranslation()
  const [showPassphrase, setShowPassphrase] = useState(false)
  const executionTarget = data.executionTarget ?? 'local'

  const getSourceSshConnection = () => {
    if (data.dataSource !== 'remote' || !data.sourceSshConnectionId) return null
    const conn = sshConnections.find((c) => c.id === data.sourceSshConnectionId)
    if (!conn) return null
    return {
      username: conn.username,
      host: conn.host,
      port: conn.port,
      defaultPath: conn.default_path,
    }
  }

  const getRepoSshConnection = () => {
    if (data.repositoryLocation !== 'ssh' || !data.repoSshConnectionId) return null
    const conn = sshConnections.find((c) => c.id === data.repoSshConnectionId)
    return conn || null
  }

  const getSourceSshConnectionForFlow = () => {
    if (data.dataSource !== 'remote' || !data.sourceSshConnectionId) return null
    const conn = sshConnections.find((c) => c.id === data.sourceSshConnectionId)
    return conn || null
  }

  const getRepoConnectionDetails = () => {
    if (data.repositoryLocation === 'ssh' && data.repoSshConnectionId) {
      const conn = sshConnections.find((c) => c.id === data.repoSshConnectionId)
      if (conn) return { host: conn.host, username: conn.username, port: conn.port }
    }
    return { host: '', username: '', port: 22 }
  }

  const repoDetails = getRepoConnectionDetails()
  const selectedAgent =
    executionTarget === 'agent' && data.agentMachineId
      ? agentMachines.find((agent) => agent.id === data.agentMachineId)
      : null
  const isEncrypted = data.encryption !== 'none'
  const hasBackupSource = data.repositoryMode === 'full' && data.sourceDirs.length > 0
  const hasBackupConfiguration =
    data.repositoryMode === 'full' &&
    (hasBackupSource || data.excludePatterns.length > 0 || Boolean(data.customFlags))

  const EMERALD = '#10b981'
  const BLUE = '#3b82f6'
  const AMBER = '#f59e0b'
  const VIOLET = '#8b5cf6'
  const ERROR = '#ef4444'

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {/* Backup Flow Preview */}
      {hasBackupSource && (
        <BackupFlowPreview
          repositoryLocation={data.repositoryLocation}
          dataSource={data.dataSource}
          repositoryPath={data.path}
          sourceDirs={data.sourceDirs}
          repoSshConnection={getRepoSshConnection()}
          sourceSshConnection={getSourceSshConnectionForFlow()}
        />
      )}

      {/* Command Preview */}
      {(data.dataSource === 'local' || data.dataSource === 'remote') && hasBackupSource && (
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

      {/* Manifest header + status chip */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <ReviewKicker>{t('wizard.review.configurationSummary')}</ReviewKicker>

        {mode === 'create' && data.repositoryMode === 'full' && (
          <Tooltip title={t('wizard.review.repositoryInitialized')} placement="top" arrow>
            <Chip
              icon={<Rocket size={11} />}
              label="Ready to Initialize"
              size="small"
              sx={{
                height: 20,
                fontSize: '0.65rem',
                fontWeight: 600,
                bgcolor: alpha(EMERALD, 0.1),
                color: EMERALD,
                border: `1px solid ${alpha(EMERALD, 0.25)}`,
                cursor: 'help',
                '& .MuiChip-icon': { color: EMERALD, ml: '6px' },
                '& .MuiChip-label': { px: '8px' },
              }}
            />
          </Tooltip>
        )}
      </Box>

      {mode === 'create' && data.repositoryMode === 'full' && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
          <Info size={14} style={{ opacity: 0.45, flexShrink: 0 }} />
          <Typography variant="body2" color="text.secondary">
            {t('wizard.review.repositoryInitialized')}
          </Typography>
        </Box>
      )}

      {/* 2x2 section card grid */}
      <ReviewSectionGrid>
        {/* REPOSITORY */}
        <ReviewSectionCard
          icon={<FolderOpen size={14} />}
          label={t('wizard.review.repository')}
          accentColor={BLUE}
        >
          <ReviewAttrRow label={t('wizard.review.name')}>
            <Typography variant="body2" fontWeight={700} fontSize="0.8rem">
              {data.name}
            </Typography>
          </ReviewAttrRow>

          <ReviewAttrRow label={t('wizard.review.mode')}>
            <Chip
              label={
                data.repositoryMode === 'full'
                  ? t('wizard.review.full')
                  : t('wizard.review.observeOnly')
              }
              size="small"
              color={data.repositoryMode === 'full' ? 'primary' : 'default'}
              sx={{ height: 17, fontSize: '0.62rem', fontWeight: 600 }}
            />
          </ReviewAttrRow>

          <ReviewAttrRow label={t('wizard.review.location')}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              {data.repositoryLocation === 'local' ? (
                <Server size={12} style={{ opacity: 0.6 }} />
              ) : (
                <Cloud size={12} style={{ opacity: 0.6 }} />
              )}
              <Typography variant="body2" fontSize="0.75rem">
                {data.repositoryLocation === 'local'
                  ? t('wizard.review.borgUiServer')
                  : t('wizard.review.sshRemote')}
              </Typography>
            </Box>
          </ReviewAttrRow>

          <ReviewAttrRow label={t('wizard.review.execution')}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              {executionTarget === 'agent' ? (
                <Laptop size={12} style={{ opacity: 0.6 }} />
              ) : (
                <Server size={12} style={{ opacity: 0.6 }} />
              )}
              <Typography variant="body2" fontSize="0.75rem">
                {executionTarget === 'agent'
                  ? t('wizard.review.managedAgent')
                  : t('wizard.review.borgUiServer')}
              </Typography>
            </Box>
          </ReviewAttrRow>

          {executionTarget === 'agent' && (
            <ReviewAttrRow label={t('wizard.review.agent')}>
              <Typography variant="body2" fontSize="0.75rem" fontWeight={500}>
                {selectedAgent?.hostname || selectedAgent?.name || t('wizard.review.notSet')}
              </Typography>
            </ReviewAttrRow>
          )}

          <ReviewAttrRow label={t('wizard.review.path')}>
            <ReviewCodePill>{data.path || t('wizard.review.notSet')}</ReviewCodePill>
          </ReviewAttrRow>
        </ReviewSectionCard>

        {/* SECURITY */}
        <ReviewSectionCard
          icon={<Shield size={14} />}
          label={t('wizard.review.security')}
          accentColor={isEncrypted ? EMERALD : ERROR}
        >
          {mode === 'create' && (
            <ReviewAttrRow label={t('wizard.review.encryption')}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.4 }}>
                {isEncrypted ? (
                  <Lock size={11} color={EMERALD} />
                ) : (
                  <Unlock size={11} color={ERROR} />
                )}
                <Chip
                  label={t(getEncryptionLabelKey(data.encryption))}
                  size="small"
                  color={isEncrypted ? 'success' : 'error'}
                  sx={{ height: 17, fontSize: '0.62rem', fontWeight: 600 }}
                />
              </Box>
            </ReviewAttrRow>
          )}

          <ReviewAttrRow label={t('wizard.review.passphrase')}>
            {data.passphrase ? (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.4 }}>
                <Typography
                  variant="body2"
                  fontFamily={showPassphrase ? 'inherit' : 'monospace'}
                  fontSize="0.75rem"
                  letterSpacing={showPassphrase ? 'normal' : '0.1em'}
                >
                  {showPassphrase ? data.passphrase : '••••••••'}
                </Typography>
                <Tooltip title={showPassphrase ? 'Hide passphrase' : 'Show passphrase'}>
                  <IconButton
                    aria-label={showPassphrase ? 'Hide passphrase' : 'Show passphrase'}
                    onClick={() => setShowPassphrase((v) => !v)}
                    size="small"
                    sx={{ p: 0.2 }}
                  >
                    {showPassphrase ? <EyeOff size={11} /> : <Eye size={11} />}
                  </IconButton>
                </Tooltip>
              </Box>
            ) : (
              <Typography variant="body2" fontSize="0.75rem" color="text.secondary">
                {t('wizard.review.passphraseNotSet')}
              </Typography>
            )}
          </ReviewAttrRow>
        </ReviewSectionCard>

        {/* DATA SOURCE - full mode only */}
        {hasBackupSource && (
          <ReviewSectionCard
            icon={data.dataSource === 'local' ? <HardDrive size={14} /> : <Laptop size={14} />}
            label={t('wizard.review.dataSource')}
            accentColor={AMBER}
          >
            <ReviewAttrRow label={t('wizard.review.source')}>
              <Typography variant="body2" fontSize="0.75rem" fontWeight={500}>
                {executionTarget === 'agent'
                  ? t('wizard.review.managedAgent')
                  : data.dataSource === 'local'
                    ? t('wizard.review.borgUiServer')
                    : t('wizard.review.remoteClient')}
              </Typography>
            </ReviewAttrRow>

            {data.dataSource === 'local' && (
              <>
                <ReviewAttrRow label={t('wizard.review.directories')}>
                  <Typography variant="body2" fontSize="0.75rem">
                    {t('wizard.review.directoriesCount', { count: data.sourceDirs.length })}
                  </Typography>
                </ReviewAttrRow>

                <ReviewAttrRow label={t('wizard.review.excludePatterns')}>
                  <Typography variant="body2" fontSize="0.75rem">
                    {t('wizard.review.directoriesCount', { count: data.excludePatterns.length })}
                  </Typography>
                </ReviewAttrRow>
              </>
            )}
          </ReviewSectionCard>
        )}

        {/* BACKUP CONFIG - full mode only */}
        {hasBackupConfiguration && (
          <ReviewSectionCard
            icon={<Settings size={14} />}
            label={t('wizard.review.backupConfiguration')}
            accentColor={VIOLET}
          >
            <ReviewAttrRow label={t('wizard.review.compression')}>
              <ReviewCodePill>{data.compression}</ReviewCodePill>
            </ReviewAttrRow>

            {data.customFlags && (
              <ReviewAttrRow label={t('wizard.review.customFlags')}>
                <ReviewCodePill>{data.customFlags}</ReviewCodePill>
              </ReviewAttrRow>
            )}
          </ReviewSectionCard>
        )}
      </ReviewSectionGrid>

      {/* Import / edit notes */}
      {mode === 'import' && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
          <Info size={14} style={{ opacity: 0.45, flexShrink: 0 }} />
          <Typography variant="body2" color="text.secondary">
            {t('wizard.review.repositoryImportNote')}
          </Typography>
        </Box>
      )}

      {mode === 'edit' && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
          <Info size={14} style={{ opacity: 0.45, flexShrink: 0 }} />
          <Typography variant="body2" color="text.secondary">
            {t('wizard.review.repositoryEditNote')}
          </Typography>
        </Box>
      )}
    </Box>
  )
}
