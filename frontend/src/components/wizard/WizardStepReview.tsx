import React, { useState } from 'react'
import { Box, Typography, Chip, IconButton, Tooltip, useTheme, alpha } from '@mui/material'
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

function getEncryptionLabelKey(encryption: string) {
  if (encryption === 'none') return 'wizard.review.encryptionNone'
  if (encryption.startsWith('repokey')) return 'wizard.review.encryptionRepokey'
  if (encryption.startsWith('keyfile')) return 'wizard.review.encryptionKeyfile'
  return 'wizard.review.encryptionNone'
}

// Colored app-icon-style badge square
function IconBadge({ icon, accentColor }: { icon: React.ReactNode; accentColor: string }) {
  return (
    <Box
      sx={{
        width: 28,
        height: 28,
        borderRadius: '8px',
        bgcolor: alpha(accentColor, 0.15),
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: accentColor,
        flexShrink: 0,
      }}
    >
      {icon}
    </Box>
  )
}

// Inline monospace pill for paths / technical values
function CodePill({ children }: { children: React.ReactNode }) {
  const theme = useTheme()
  return (
    <Tooltip title={children} placement="top">
      <Typography
        component="span"
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.72rem',
          px: 0.75,
          py: 0.15,
          borderRadius: '4px',
          bgcolor: alpha(theme.palette.text.primary, theme.palette.mode === 'dark' ? 0.08 : 0.06),
          color: 'text.primary',
          maxWidth: '100%',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          display: 'inline-block',
          verticalAlign: 'middle',
          cursor: 'default',
          lineHeight: 1.6,
        }}
      >
        {children}
      </Typography>
    </Tooltip>
  )
}

// Attribute row within a section card
function AttrRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 1,
        minWidth: 0,
      }}
    >
      <Typography
        variant="caption"
        sx={{ color: 'text.disabled', fontSize: '0.7rem', flexShrink: 0 }}
      >
        {label}
      </Typography>
      <Box
        sx={{
          minWidth: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 0.5,
          flexWrap: 'wrap',
          justifyContent: 'flex-end',
        }}
      >
        {children}
      </Box>
    </Box>
  )
}

// Section card: icon badge + label + rows
function SectionCard({
  icon,
  label,
  accentColor,
  children,
}: {
  icon: React.ReactNode
  label: string
  accentColor: string
  children: React.ReactNode
}) {
  const theme = useTheme()
  return (
    <Box
      sx={{
        borderRadius: 2,
        bgcolor: alpha(accentColor, theme.palette.mode === 'dark' ? 0.07 : 0.05),
        p: 1.5,
        display: 'flex',
        flexDirection: 'column',
        gap: 1.25,
        minWidth: 0,
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <IconBadge icon={icon} accentColor={accentColor} />
        <Typography
          variant="caption"
          sx={{
            color: 'text.secondary',
            fontWeight: 700,
            fontSize: '0.68rem',
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
          }}
        >
          {label}
        </Typography>
      </Box>

      {/* Attribute rows */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.6 }}>{children}</Box>
    </Box>
  )
}

export default function WizardStepReview({ mode, data, sshConnections }: WizardStepReviewProps) {
  const { t } = useTranslation()
  const [showPassphrase, setShowPassphrase] = useState(false)

  const getSourceSshConnection = () => {
    if (data.dataSource !== 'remote' || !data.sourceSshConnectionId) return null
    const conn = sshConnections.find((c) => c.id === data.sourceSshConnectionId)
    if (!conn) return null
    return { username: conn.username, host: conn.host, port: conn.port }
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
  const isEncrypted = data.encryption !== 'none'

  const EMERALD = '#10b981'
  const BLUE = '#3b82f6'
  const AMBER = '#f59e0b'
  const VIOLET = '#8b5cf6'
  const ERROR = '#ef4444'

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

      {/* Command Preview */}
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

      {/* Manifest header + status chip */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography
          variant="caption"
          sx={{
            color: 'text.disabled',
            fontWeight: 700,
            fontSize: '0.6rem',
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
          }}
        >
          {t('wizard.review.configurationSummary')}
        </Typography>

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

      {/* 2×2 section card grid */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
          gap: 1.25,
          minWidth: 0,
          overflow: 'hidden',
        }}
      >
        {/* REPOSITORY */}
        <SectionCard
          icon={<FolderOpen size={14} />}
          label={t('wizard.review.repository')}
          accentColor={BLUE}
        >
          <AttrRow label={t('wizard.review.name')}>
            <Typography variant="body2" fontWeight={700} fontSize="0.8rem">
              {data.name}
            </Typography>
          </AttrRow>

          <AttrRow label={t('wizard.review.mode')}>
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
          </AttrRow>

          <AttrRow label={t('wizard.review.location')}>
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
          </AttrRow>

          <AttrRow label={t('wizard.review.path')}>
            <CodePill>{data.path || t('wizard.review.notSet')}</CodePill>
          </AttrRow>
        </SectionCard>

        {/* SECURITY */}
        <SectionCard
          icon={<Shield size={14} />}
          label={t('wizard.review.security')}
          accentColor={isEncrypted ? EMERALD : ERROR}
        >
          {mode === 'create' && (
            <AttrRow label={t('wizard.review.encryption')}>
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
            </AttrRow>
          )}

          <AttrRow label={t('wizard.review.passphrase')}>
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
          </AttrRow>
        </SectionCard>

        {/* DATA SOURCE — full mode only */}
        {data.repositoryMode === 'full' && (
          <SectionCard
            icon={data.dataSource === 'local' ? <HardDrive size={14} /> : <Laptop size={14} />}
            label={t('wizard.review.dataSource')}
            accentColor={AMBER}
          >
            <AttrRow label={t('wizard.review.source')}>
              <Typography variant="body2" fontSize="0.75rem" fontWeight={500}>
                {data.dataSource === 'local'
                  ? t('wizard.review.borgUiServer')
                  : t('wizard.review.remoteClient')}
              </Typography>
            </AttrRow>

            {data.dataSource === 'local' && (
              <>
                <AttrRow label={t('wizard.review.directories')}>
                  <Typography variant="body2" fontSize="0.75rem">
                    {t('wizard.review.directoriesCount', { count: data.sourceDirs.length })}
                  </Typography>
                </AttrRow>

                <AttrRow label={t('wizard.review.excludePatterns')}>
                  <Typography variant="body2" fontSize="0.75rem">
                    {t('wizard.review.directoriesCount', { count: data.excludePatterns.length })}
                  </Typography>
                </AttrRow>
              </>
            )}
          </SectionCard>
        )}

        {/* BACKUP CONFIG — full mode only */}
        {data.repositoryMode === 'full' && (
          <SectionCard
            icon={<Settings size={14} />}
            label={t('wizard.review.backupConfiguration')}
            accentColor={VIOLET}
          >
            <AttrRow label={t('wizard.review.compression')}>
              <CodePill>{data.compression}</CodePill>
            </AttrRow>

            {data.customFlags && (
              <AttrRow label={t('wizard.review.customFlags')}>
                <CodePill>{data.customFlags}</CodePill>
              </AttrRow>
            )}
          </SectionCard>
        )}
      </Box>

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
