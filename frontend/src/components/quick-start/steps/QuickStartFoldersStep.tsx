import { useCallback, useState } from 'react'
import { Box, Button, Chip, Stack, Typography } from '@mui/material'
import { Folder } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import AppTemplateFolderPanel from '../../app-templates/AppTemplateFolderPanel'
import type { AppScanTarget } from '../../app-templates/appTemplates'
import PathSelectorField from '../../shared/PathSelectorField'
import type { QuickStartStepProps } from '../quickStartState'
import { agentIsOnline, agentLabel, useManagedAgent } from '../quickStartAgent'
import { sshBrowseConfig, useSshConnection } from '../quickStartSsh'

export default function QuickStartFoldersStep({ answers, onChange }: QuickStartStepProps) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState('')
  const remote = answers.sourceKind === 'ssh'
  const connection = useSshConnection(remote ? answers.sourceConnectionId : '')
  const onAgent = answers.sourceKind === 'agent'
  const agent = useManagedAgent(onAgent ? answers.sourceAgentId : '')

  // The app's folder stays first: its excludes and check script are built from it.
  const setAppPaths = useCallback(
    (root: string, extraPaths: string[]) => onChange({ sourcePaths: [root, ...extraPaths] }),
    [onChange]
  )
  const scanTarget: AppScanTarget | null =
    answers.sourceKind === 'server'
      ? { source_type: 'local', source_ssh_connection_id: null }
      : answers.sourceKind === 'ssh' && answers.sourceConnectionId !== ''
        ? { source_type: 'remote', source_ssh_connection_id: answers.sourceConnectionId }
        : null

  const addPaths = (paths: string[]) => {
    const next = [...answers.sourcePaths]
    for (const path of paths.map((value) => value.trim()).filter(Boolean)) {
      if (!next.includes(path)) next.push(path)
    }
    onChange({ sourcePaths: next })
    setDraft('')
  }

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h6" component="h3">
          {t('quickStart.folders.title')}
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          {remote && connection
            ? t('quickStart.folders.remoteHint', {
                machine: `${connection.username}@${connection.host}`,
              })
            : onAgent && agent
              ? agentIsOnline(agent)
                ? t('quickStart.folders.remoteHint', { machine: agentLabel(agent) })
                : t('quickStart.agent.offlineBrowse', { machine: agentLabel(agent) })
              : t('quickStart.folders.hint')}
        </Typography>
      </Box>

      {answers.app && (
        <AppTemplateFolderPanel
          template={answers.app}
          target={scanTarget}
          root={answers.sourcePaths[0] ?? ''}
          extraPaths={answers.sourcePaths.slice(1)}
          onPathsChange={setAppPaths}
          excludes={answers.appExcludes}
          onExcludesChange={(appExcludes) => onChange({ appExcludes })}
        />
      )}

      <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
        <PathSelectorField
          label={t('quickStart.folders.pathLabel')}
          value={draft}
          onChange={setDraft}
          placeholder={remote || onAgent ? '/home' : '/local/home'}
          multiSelect
          connectionType={remote ? 'ssh' : onAgent ? 'agent' : 'local'}
          sshConfig={remote ? sshBrowseConfig(connection) : undefined}
          agentId={agent?.id}
          agentName={agent ? agentLabel(agent) : undefined}
          agentDefaultPath={agent?.default_path}
          browseButtonDisabled={onAgent && !agentIsOnline(agent)}
          initialPath={remote ? connection?.default_path || '/' : undefined}
          showSshMountPoints={false}
          onSelectPaths={addPaths}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              addPaths([draft])
            }
          }}
        />
        <Button
          variant="outlined"
          onClick={() => addPaths([draft])}
          disabled={!draft.trim()}
          sx={{ flexShrink: 0, height: 40 }}
        >
          {t('quickStart.folders.add')}
        </Button>
      </Stack>

      {answers.sourcePaths.length === 0 ? (
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {t('quickStart.folders.empty')}
        </Typography>
      ) : (
        <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 1 }}>
          {answers.sourcePaths.map((path) => (
            <Chip
              key={path}
              icon={<Folder size={14} />}
              label={path}
              onDelete={() =>
                onChange({ sourcePaths: answers.sourcePaths.filter((item) => item !== path) })
              }
              sx={{ maxWidth: '100%', fontFamily: 'monospace' }}
            />
          ))}
        </Stack>
      )}
    </Stack>
  )
}
