import { useCallback, useState } from 'react'
import { Box, Button, IconButton, Paper, Stack, Tooltip, Typography } from '@mui/material'
import { HardDrive, Plus, Server, Trash2 } from 'lucide-react'
import type { TFunction } from 'i18next'

import AppLogo from '../../../components/app-templates/AppLogo'
import AppTemplateFolderPanel from '../../../components/app-templates/AppTemplateFolderPanel'
import AppTemplateSelect from '../../../components/app-templates/AppTemplateSelect'
import {
  appExcludePatterns,
  checksBackedUpDumps,
  defaultAppExcludes,
  renderAppScript,
  useAppTemplates,
  type AppScanTarget,
} from '../../../components/app-templates/appTemplates'
import DestinationSelect from '../../../components/shared/DestinationSelect'
import PathSelectorField from '../../../components/shared/PathSelectorField'
import SshConnectionSelect from '../../../components/shared/SshConnectionSelect'
import type { AppTemplate } from '../../../services/api'
import type { SourceLocation } from '../../../types'
import type { SSHConnection } from '../types'
import type { SourceScriptCreateInput } from './types'

interface AppSourcePanelProps {
  sshConnections: SSHConnection[]
  /** 'local' or `remote:<id>`; agents can't be scanned for apps. */
  sourceKey: string
  onSourceKeyChange: (key: 'local' | `remote:${number}`) => void
  /** App sources already in the plan draft. */
  appLocations: SourceLocation[]
  onAdd: (location: SourceLocation, script: SourceScriptCreateInput | null) => void
  onRemove: (location: SourceLocation) => void
  machineLabel: (location: SourceLocation) => string
  t: TFunction
}

/** The Apps tab of the source chooser: find an app, pick its parts, add it as a source. */
export default function AppSourcePanel({
  sshConnections,
  sourceKey,
  onSourceKeyChange,
  appLocations,
  onAdd,
  onRemove,
  machineLabel,
  t,
}: AppSourcePanelProps) {
  const { templates } = useAppTemplates()
  const [template, setTemplate] = useState<AppTemplate | null>(null)
  const [root, setRoot] = useState('')
  const [rootIncluded, setRootIncluded] = useState(true)
  const [extraPaths, setExtraPaths] = useState<string[]>([])
  const [excludes, setExcludes] = useState<string[]>([])
  const [container, setContainer] = useState('')

  const remoteId = sourceKey.startsWith('remote:') ? Number(sourceKey.split(':')[1]) : null
  const connection = sshConnections.find((item) => item.id === remoteId)
  const target: AppScanTarget =
    remoteId === null
      ? { source_type: 'local', source_ssh_connection_id: null }
      : { source_type: 'remote', source_ssh_connection_id: remoteId }

  const reset = (next: AppTemplate | null) => {
    setTemplate(next)
    setRoot('')
    setRootIncluded(true)
    setExtraPaths([])
    setExcludes(next ? defaultAppExcludes(next) : [])
  }
  const setPaths = useCallback((nextRoot: string, nextExtras: string[]) => {
    setRoot(nextRoot)
    setRootIncluded(true)
    setExtraPaths(nextExtras)
  }, [])

  const add = () => {
    if (!template || !root.trim()) return
    const appRoot = root.trim()
    const paths = [...(rootIncluded ? [appRoot] : []), ...extraPaths]
    if (paths.length === 0) return
    const location: SourceLocation = {
      source_type: remoteId === null ? 'local' : 'remote',
      source_ssh_connection_id: remoteId,
      agent_machine_id: null,
      paths,
      app: {
        template_id: template.id,
        template_version: template.version,
        display_name: template.name,
        root: appRoot,
        exclude_patterns: rootIncluded ? appExcludePatterns(appRoot, excludes) : [],
        // Runs where the app is: over SSH for a remote source.
        script_execution_target: 'source',
      },
    }
    const checkScript = template.pre_backup_script
    const content =
      rootIncluded && checksBackedUpDumps(template, excludes)
        ? renderAppScript(template, appRoot, container)
        : null
    onAdd(
      location,
      checkScript && content
        ? {
            name: `${checkScript.name}: ${template.name}`,
            description: checkScript.description,
            content,
            timeout: checkScript.timeout,
            run_on: 'always',
            category: 'template',
          }
        : null
    )
    reset(null)
  }

  const machineOptions = [
    {
      key: 'local',
      icon: <HardDrive size={16} />,
      label: t('backupPlans.sourceChooser.borgUiServer'),
      description: t('backupPlans.sourceChooser.localSourceDescription'),
    },
    {
      key: 'remote',
      icon: <Server size={16} />,
      label: t('backupPlans.sourceChooser.remoteMachine'),
      description:
        sshConnections.length > 0
          ? t('backupPlans.sourceChooser.remoteMachineDescription')
          : t('backupPlans.sourceChooser.noRemoteMachines'),
      disabled: sshConnections.length === 0,
    },
  ]

  return (
    <Stack spacing={2.5}>
      {appLocations.length > 0 && (
        <Stack spacing={1}>
          <Typography variant="subtitle2">{t('appTemplates.tab.inPlan')}</Typography>
          {appLocations.map((location) => {
            const app = location.app!
            const known = templates.find((item) => item.id === app.template_id)
            return (
              <Paper
                key={`${machineLabel(location)}:${app.template_id}:${app.root}`}
                variant="outlined"
                sx={{ px: 1.5, py: 1, display: 'flex', alignItems: 'center', gap: 1.5 }}
              >
                <Box sx={{ flexShrink: 0 }}>{known && <AppLogo app={known} size={22} />}</Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="subtitle2">{app.display_name}</Typography>
                  <Typography
                    variant="caption"
                    component="p"
                    sx={{ color: 'text.secondary', overflowWrap: 'anywhere' }}
                  >
                    {machineLabel(location)} ·{' '}
                    {t('appTemplates.tab.folderCount', { count: location.paths.length })}
                  </Typography>
                </Box>
                <Tooltip title={t('appTemplates.tab.remove', { app: app.display_name })}>
                  <IconButton
                    size="small"
                    aria-label={t('appTemplates.tab.remove', { app: app.display_name })}
                    onClick={() => onRemove(location)}
                  >
                    <Trash2 size={14} />
                  </IconButton>
                </Tooltip>
              </Paper>
            )
          })}
        </Stack>
      )}

      <Stack spacing={2}>
        <DestinationSelect
          value={remoteId === null ? 'local' : 'remote'}
          onChange={(key) => {
            if (key === 'local') onSourceKeyChange('local')
            else if (sshConnections.length > 0)
              onSourceKeyChange(`remote:${remoteId ?? sshConnections[0].id}`)
            reset(template)
          }}
          destinations={machineOptions}
          label={t('appTemplates.tab.runsOn')}
        />
        {remoteId !== null && (
          <SshConnectionSelect
            value={remoteId}
            onChange={(id) => {
              onSourceKeyChange(`remote:${id}`)
              reset(template)
            }}
            connections={sshConnections}
            label={t('backupPlans.sourceChooser.selectRemoteMachine')}
            emptyMessage={t('backupPlans.sourceChooser.noRemoteMachines')}
            hideEmptyAlert
          />
        )}
        <AppTemplateSelect templates={templates} value={template} onChange={reset} />
      </Stack>

      {template && (
        <AppTemplateFolderPanel
          template={template}
          target={target}
          root={root}
          rootIncluded={rootIncluded}
          onRootIncludedChange={setRootIncluded}
          extraPaths={extraPaths}
          onPathsChange={setPaths}
          onContainerChange={setContainer}
          excludes={excludes}
          onExcludesChange={setExcludes}
        />
      )}

      {template && (
        <PathSelectorField
          label={t('appTemplates.tab.folder')}
          value={root}
          onChange={(value) => {
            setRoot(value)
            setRootIncluded(true)
          }}
          placeholder={remoteId === null ? '/local/srv/immich' : '/srv/immich'}
          connectionType={remoteId === null ? 'local' : 'ssh'}
          sshConfig={
            connection
              ? {
                  ssh_key_id: connection.ssh_key_id,
                  host: connection.host,
                  username: connection.username,
                  port: connection.port,
                }
              : undefined
          }
          showSshMountPoints={false}
        />
      )}

      {template && (
        <Box>
          <Button
            variant="outlined"
            startIcon={<Plus size={16} />}
            onClick={add}
            disabled={!root.trim() || (!rootIncluded && extraPaths.length === 0)}
          >
            {t('appTemplates.tab.add', { app: template.name })}
          </Button>
        </Box>
      )}
    </Stack>
  )
}
