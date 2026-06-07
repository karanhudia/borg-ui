import { useState } from 'react'
import { alpha, Box, Button, Chip, Stack, TextField, Typography } from '@mui/material'
import {
  ChevronDown,
  ChevronUp,
  Container as ContainerIcon,
  Database,
  FolderOpen,
  HardDrive,
  Laptop,
  Server,
} from 'lucide-react'

import ExcludePatternInput from '../../../components/ExcludePatternInput'
import { SourceSelectionDialog } from './SourceSelectionDialog'
import type { SourceLocation } from '../../../types'
import type { BackupPlanWizardStepProps } from './types'
import type { SSHConnection, WizardState } from '../types'

const DATABASE_DUMP_ROOT = '/var/tmp/borg-ui/database-dumps'

type SourceStepProps = Pick<
  BackupPlanWizardStepProps,
  | 'wizardState'
  | 'sshConnections'
  | 'agentMachines'
  | 'fullRepositories'
  | 'scripts'
  | 'loadingScripts'
  | 'updateState'
  | 'openExcludeExplorer'
  | 'onCreateScript'
  | 't'
> & {
  canUseManagedAgents?: boolean
  canUseMixedSourceTypes?: boolean
  canUseDatabaseDiscovery?: boolean
  canUseContainerBackups?: boolean
}

export function SourceStep({
  wizardState,
  sshConnections,
  agentMachines,
  fullRepositories,
  scripts,
  loadingScripts,
  canUseManagedAgents = true,
  canUseMixedSourceTypes = true,
  canUseDatabaseDiscovery = true,
  canUseContainerBackups = true,
  updateState,
  openExcludeExplorer,
  onCreateScript,
  t,
}: SourceStepProps) {
  const [sourceDialogOpen, setSourceDialogOpen] = useState(false)
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({})
  const sourceLocations = getWizardSourceLocations(wizardState)
  const sourcePaths = sourceLocations.flatMap((location) => location.paths)
  const hasSources = sourcePaths.length > 0
  const hasDatabaseSource = sourceLocations.some((location) => Boolean(location.database))
  const hasContainerSource = sourceLocations.some((location) => Boolean(location.container))
  const isLegacyDatabaseSource =
    !hasDatabaseSource &&
    !hasContainerSource &&
    sourcePaths.length > 0 &&
    sourcePaths.every(isDatabaseDumpPath)
  const hasFileSource = sourceLocations.some(
    (location) =>
      !location.database &&
      !location.container &&
      !(isLegacyDatabaseSource && location.paths.every(isDatabaseDumpPath))
  )
  const isDatabaseSource =
    (hasDatabaseSource && !hasFileSource && !hasContainerSource) || isLegacyDatabaseSource
  const isContainerSource = hasContainerSource && !hasDatabaseSource && !hasFileSource
  const sourceKindCount = [
    hasDatabaseSource || isLegacyDatabaseSource,
    hasContainerSource,
    hasFileSource,
  ].filter(Boolean).length
  const sourceKindLabel =
    sourceKindCount > 1
      ? t('backupPlans.sourceChooser.mixedSources')
      : isDatabaseSource
        ? t('backupPlans.sourceChooser.databaseTitle')
        : isContainerSource
          ? t('backupPlans.sourceChooser.containerTitle')
          : t('backupPlans.sourceChooser.filesTitle')

  return (
    <Stack spacing={3}>
      <TextField
        label={t('backupPlans.wizard.fields.planName')}
        value={wizardState.name}
        onChange={(event) => updateState({ name: event.target.value })}
        required
        fullWidth
      />
      <TextField
        label={t('backupPlans.wizard.fields.description')}
        value={wizardState.description}
        onChange={(event) => updateState({ description: event.target.value })}
        multiline
        rows={2}
        fullWidth
      />
      <Box
        sx={{
          border: 1,
          borderColor: 'divider',
          borderRadius: 2,
          bgcolor: (theme) =>
            theme.palette.mode === 'dark'
              ? alpha(theme.palette.common.white, 0.02)
              : alpha(theme.palette.common.black, 0.015),
          p: 2,
        }}
      >
        <Stack spacing={hasSources ? 1.5 : 0}>
          <Stack
            direction="row"
            spacing={1.5}
            alignItems="center"
            justifyContent="space-between"
            sx={{ minWidth: 0 }}
          >
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ minWidth: 0 }}>
              <Box
                sx={{
                  alignItems: 'center',
                  bgcolor: 'background.paper',
                  border: 1,
                  borderColor: 'divider',
                  borderRadius: 1.5,
                  color: 'text.secondary',
                  display: 'flex',
                  flexShrink: 0,
                  height: 36,
                  justifyContent: 'center',
                  width: 36,
                }}
              >
                {isDatabaseSource ? (
                  <Database size={18} />
                ) : isContainerSource ? (
                  <ContainerIcon size={18} />
                ) : (
                  <FolderOpen size={18} />
                )}
              </Box>
              <Stack spacing={0.5} sx={{ minWidth: 0 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, lineHeight: 1.2 }}>
                  {t('backupPlans.sourceChooser.summaryTitle')}
                </Typography>
                {hasSources ? (
                  <Stack
                    direction="row"
                    spacing={0.75}
                    flexWrap="wrap"
                    useFlexGap
                    sx={{ minWidth: 0 }}
                  >
                    <Chip size="small" label={sourceKindLabel} />
                    <Chip
                      size="small"
                      variant="outlined"
                      label={t('backupPlans.sourceChooser.pathCount', {
                        count: sourcePaths.length,
                      })}
                    />
                  </Stack>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    {t('backupPlans.sourceChooser.summaryEmpty')}
                  </Typography>
                )}
              </Stack>
            </Stack>
            <Button
              variant="text"
              size="small"
              onClick={() => setSourceDialogOpen(true)}
              sx={{ flexShrink: 0, textTransform: 'none', fontWeight: 500 }}
            >
              {hasSources
                ? t('backupPlans.sourceChooser.edit')
                : t('backupPlans.sourceChooser.chooseSource')}
            </Button>
          </Stack>
          {hasSources && (
            <Stack spacing={1}>
              {sourceLocations.map((location) => {
                const groupKey = sourceLocationKey(location)
                const isExpanded = expandedGroups[groupKey] ?? false
                const commonPrefix = commonDirectoryPrefix(location.paths)
                const databaseLivePath = location.database?.detected_source_path?.trim()
                const toggle = () =>
                  setExpandedGroups((prev) => ({ ...prev, [groupKey]: !isExpanded }))

                return (
                  <Box
                    key={groupKey}
                    sx={{
                      bgcolor: 'background.paper',
                      border: 1,
                      borderColor: 'divider',
                      borderRadius: 1.5,
                      overflow: 'hidden',
                    }}
                  >
                    <Box
                      role="button"
                      tabIndex={0}
                      aria-expanded={isExpanded}
                      onClick={toggle}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          toggle()
                        }
                      }}
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 1,
                        py: 1,
                        px: 1.25,
                        cursor: 'pointer',
                        color: 'text.secondary',
                        transition: 'background-color 120ms ease',
                        '&:hover': { bgcolor: 'action.hover' },
                        '&:focus-visible': {
                          outline: (theme) => `2px solid ${theme.palette.primary.main}`,
                          outlineOffset: -2,
                        },
                      }}
                    >
                      {location.container ? (
                        <ContainerIcon size={14} style={{ flexShrink: 0 }} />
                      ) : location.source_type === 'remote' ? (
                        <Server size={14} style={{ flexShrink: 0 }} />
                      ) : location.source_type === 'agent' ? (
                        <Laptop size={14} style={{ flexShrink: 0 }} />
                      ) : (
                        <HardDrive size={14} style={{ flexShrink: 0 }} />
                      )}
                      <Typography variant="caption" sx={{ fontWeight: 600, flexShrink: 0 }} noWrap>
                        {sourceLocationLabel(location, sshConnections, agentMachines, t)}
                      </Typography>
                      <Typography variant="caption" sx={{ flexShrink: 0 }}>
                        ·
                      </Typography>
                      <Typography variant="caption" sx={{ flexShrink: 0 }}>
                        {t('backupPlans.sourceChooser.pathCount', {
                          count: location.paths.length,
                        })}
                      </Typography>
                      {location.database && (
                        <Chip
                          size="small"
                          variant="outlined"
                          label={location.database.display_name}
                          sx={{ height: 20, flexShrink: 0 }}
                        />
                      )}
                      {location.container && (
                        <Chip
                          size="small"
                          variant="outlined"
                          label={location.container.display_name}
                          sx={{ height: 20, flexShrink: 0 }}
                        />
                      )}
                      {location.snapshot && (
                        <Chip
                          size="small"
                          variant="outlined"
                          label={t('backupPlans.sourceChooser.snapshotChip', {
                            provider: location.snapshot.provider,
                          })}
                          sx={{ height: 20, flexShrink: 0 }}
                        />
                      )}
                      {databaseLivePath ? (
                        <>
                          <Typography variant="caption" sx={{ flexShrink: 0 }}>
                            {t('backupPlans.sourceChooser.databaseLivePath')}
                          </Typography>
                          <Typography
                            variant="caption"
                            title={databaseLivePath}
                            sx={{
                              fontFamily:
                                'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
                              color: 'text.primary',
                              minWidth: 0,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {databaseLivePath}
                          </Typography>
                        </>
                      ) : commonPrefix ? (
                        <>
                          <Typography variant="caption" sx={{ flexShrink: 0 }}>
                            {t('backupPlans.sourceChooser.inPrefix')}
                          </Typography>
                          <Typography
                            variant="caption"
                            title={commonPrefix}
                            sx={{
                              fontFamily:
                                'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
                              color: 'text.primary',
                              minWidth: 0,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              direction: 'rtl',
                              textAlign: 'left',
                            }}
                          >
                            {commonPrefix}
                          </Typography>
                        </>
                      ) : null}
                      <Box sx={{ flex: 1 }} />
                      {isExpanded ? (
                        <ChevronUp size={14} style={{ flexShrink: 0 }} />
                      ) : (
                        <ChevronDown size={14} style={{ flexShrink: 0 }} />
                      )}
                    </Box>
                    {isExpanded && (
                      <Box sx={{ borderTop: 1, borderColor: 'divider', px: 1.25, py: 1 }}>
                        {location.container ? (
                          <ContainerSourcePathDetails location={location} t={t} />
                        ) : location.database ? (
                          <DatabaseSourcePathDetails location={location} t={t} />
                        ) : (
                          <Stack spacing={0.25} sx={{ pl: 3 }}>
                            {location.paths.map((path) => {
                              const display = commonPrefix
                                ? path.slice(commonPrefix.length) || path
                                : path
                              return (
                                <Typography
                                  key={path}
                                  variant="body2"
                                  title={path}
                                  sx={{
                                    fontSize: '0.8125rem',
                                    color: 'text.primary',
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap',
                                  }}
                                >
                                  {display}
                                </Typography>
                              )
                            })}
                          </Stack>
                        )}
                      </Box>
                    )}
                  </Box>
                )
              })}
            </Stack>
          )}
        </Stack>
      </Box>
      <ExcludePatternInput
        patterns={wizardState.excludePatterns}
        onChange={(excludePatterns) => updateState({ excludePatterns })}
        onBrowseClick={openExcludeExplorer}
      />
      <SourceSelectionDialog
        open={sourceDialogOpen}
        wizardState={wizardState}
        sshConnections={sshConnections}
        agentMachines={agentMachines}
        fullRepositories={fullRepositories}
        scripts={scripts}
        loadingScripts={loadingScripts}
        canUseManagedAgents={canUseManagedAgents}
        canUseMixedSourceTypes={canUseMixedSourceTypes}
        canUseDatabaseDiscovery={canUseDatabaseDiscovery}
        canUseContainerBackups={canUseContainerBackups}
        updateState={updateState}
        onCreateScript={onCreateScript}
        onClose={() => setSourceDialogOpen(false)}
        t={t}
      />
    </Stack>
  )
}

function sourceLocationKey(location: SourceLocation) {
  const suffix = location.container
    ? `:container:${location.container.container_name}:${location.container.export_path}`
    : location.database
      ? `:database:${location.database.template_id}`
      : ''
  if (location.source_type === 'agent') {
    return `agent:${location.agent_machine_id || 'agent'}${suffix}`
  }
  return `${location.source_type}:${location.source_ssh_connection_id || 'local'}${suffix}`
}

function commonDirectoryPrefix(paths: string[]): string {
  if (paths.length === 0) return ''
  if (paths.length === 1) {
    const lastSlash = paths[0].lastIndexOf('/')
    return lastSlash > 0 ? paths[0].slice(0, lastSlash + 1) : ''
  }
  const segments = paths.map((path) => path.split('/'))
  const minLength = Math.min(...segments.map((parts) => parts.length))
  let common = 0
  for (let i = 0; i < minLength; i++) {
    const candidate = segments[0][i]
    if (segments.every((parts) => parts[i] === candidate)) {
      common += 1
    } else {
      break
    }
  }
  if (common === minLength) common = minLength - 1
  if (common < 2) return ''
  return segments[0].slice(0, common).join('/') + '/'
}

function isDatabaseDumpPath(sourceDirectory: string): boolean {
  return (
    sourceDirectory === DATABASE_DUMP_ROOT || sourceDirectory.startsWith(`${DATABASE_DUMP_ROOT}/`)
  )
}

function getWizardSourceLocations(wizardState: WizardState): SourceLocation[] {
  if (wizardState.sourceLocations?.length) return wizardState.sourceLocations
  if (wizardState.sourceDirectories.length === 0) return []
  if (wizardState.sourceType === 'remote' && wizardState.sourceSshConnectionId) {
    return [
      {
        source_type: 'remote',
        source_ssh_connection_id: Number(wizardState.sourceSshConnectionId),
        paths: wizardState.sourceDirectories,
      },
    ]
  }
  return [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      paths: wizardState.sourceDirectories,
    },
  ]
}

function sourceLocationLabel(
  location: SourceLocation,
  sshConnections: SSHConnection[],
  agentMachines: SourceStepProps['agentMachines'],
  t: SourceStepProps['t']
) {
  if (location.source_type === 'local') return t('backupPlans.sourceChooser.borgUiServer')
  if (location.source_type === 'agent') {
    const agent = agentMachines.find((item) => item.id === location.agent_machine_id)
    if (agent) return agent.hostname || agent.name
    return t('backupPlans.sourceChooser.agentFallback', {
      id: location.agent_machine_id,
    })
  }
  const connection = sshConnections.find((item) => item.id === location.source_ssh_connection_id)
  return connection
    ? `${connection.username}@${connection.host}`
    : t('backupPlans.wizard.review.connectionFallback', {
        id: location.source_ssh_connection_id,
      })
}

function databaseBackupPathLabel(location: SourceLocation) {
  const backupPaths =
    location.database?.backup_paths?.filter((path) => path.trim().length > 0) || []
  return (backupPaths.length > 0 ? backupPaths : location.paths).join(', ')
}

function containerBackupPathLabel(location: SourceLocation) {
  return location.container?.export_path || location.paths.join(', ')
}

function DatabaseSourcePathDetails({
  location,
  t,
}: {
  location: SourceLocation
  t: SourceStepProps['t']
}) {
  const database = location.database
  if (!database) return null

  const livePath = database.detected_source_path?.trim()
  const backupPathLabel = databaseBackupPathLabel(location)

  return (
    <Stack spacing={0.75} sx={{ pl: 3, minWidth: 0 }}>
      <Typography variant="subtitle2" sx={{ fontSize: '0.8125rem', fontWeight: 700 }}>
        {database.display_name}
      </Typography>
      {livePath && (
        <DatabasePathLine
          label={t('backupPlans.sourceChooser.databaseLivePath')}
          value={livePath}
        />
      )}
      <DatabasePathLine
        label={t('backupPlans.sourceChooser.databaseBackupPaths')}
        value={backupPathLabel}
      />
    </Stack>
  )
}

function ContainerSourcePathDetails({
  location,
  t,
}: {
  location: SourceLocation
  t: SourceStepProps['t']
}) {
  const container = location.container
  if (!container) return null

  return (
    <Stack spacing={0.75} sx={{ pl: 3, minWidth: 0 }}>
      <Typography variant="subtitle2" sx={{ fontSize: '0.8125rem', fontWeight: 700 }}>
        {container.display_name}
      </Typography>
      {container.image && (
        <DatabasePathLine
          label={t('backupPlans.sourceChooser.containerImage')}
          value={container.image}
        />
      )}
      <DatabasePathLine
        label={t('backupPlans.sourceChooser.containerBackupPath')}
        value={containerBackupPathLabel(location)}
      />
    </Stack>
  )
}

function DatabasePathLine({ label, value }: { label: string; value: string }) {
  return (
    <Stack spacing={0.15} sx={{ minWidth: 0 }}>
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
        {label}
      </Typography>
      <Typography
        variant="body2"
        title={value}
        sx={{
          color: 'text.primary',
          fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
          fontSize: '0.8125rem',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {value}
      </Typography>
    </Stack>
  )
}
