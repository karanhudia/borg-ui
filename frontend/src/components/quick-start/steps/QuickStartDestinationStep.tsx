import { useEffect, useRef } from 'react'
import { Alert, Stack, Typography } from '@mui/material'
import { HardDrive, Laptop, Server } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import PathSelectorField from '../../shared/PathSelectorField'
import QuickStartChoiceCard from '../QuickStartChoiceCard'
import QuickStartSshConnect from '../QuickStartSshConnect'
import {
  agentIsOnline,
  agentLabel,
  suggestedAgentDestinationPath,
  useManagedAgent,
} from '../quickStartAgent'
import { sshBrowseConfig, useSshBasePath, useSshConnection } from '../quickStartSsh'
import {
  destinationInsideSource,
  suggestedDestinationPath,
  suggestedRemoteDestinationPath,
  type QuickStartStepProps,
} from '../quickStartState'

export default function QuickStartDestinationStep({
  answers,
  onChange,
  canAddMachine = false,
  onBusyChange,
}: QuickStartStepProps) {
  const { t } = useTranslation()
  const inside = destinationInsideSource(answers)
  const remote = answers.destinationKind === 'ssh'
  const connection = useSshConnection(remote ? answers.destinationConnectionId : '')
  const basePath = useSshBasePath(connection)
  const name = answers.name || 'backup'
  const onAgent = answers.destinationKind === 'agent'
  const agent = useManagedAgent(onAgent ? answers.sourceAgentId : '')

  // Suggest a path once per chosen connection, once its base path is known: a
  // machine added in this step is not in the list until the refetch lands, and
  // without a saved default path the machine is asked for its home folder.
  const suggestedFor = useRef<number | null>(null)
  useEffect(() => {
    if (!connection) {
      // Leaving SSH and coming back to the same machine suggests again.
      suggestedFor.current = null
      return
    }
    if (!basePath || suggestedFor.current === connection.id) return
    suggestedFor.current = connection.id
    if (!answers.destinationPath) {
      onChange({ destinationPath: suggestedRemoteDestinationPath(name, basePath) })
    }
  }, [connection, basePath, answers.destinationPath, name, onChange])

  // Same for the agent: its default path is only known once it has loaded.
  const suggestedForAgent = useRef<number | null>(null)
  useEffect(() => {
    if (!agent || suggestedForAgent.current === agent.id) return
    suggestedForAgent.current = agent.id
    if (!answers.destinationPath) {
      const destinationPath = suggestedAgentDestinationPath(name, agent, answers.sourcePaths)
      if (destinationPath) onChange({ destinationPath })
    }
  }, [agent, answers.destinationPath, answers.sourcePaths, name, onChange])

  if (onAgent) {
    return (
      <Stack spacing={2}>
        <Typography variant="h6" component="h3">
          {t('quickStart.destination.title')}
        </Typography>
        <Stack spacing={1.5} role="radiogroup" aria-label={t('quickStart.destination.title')}>
          <QuickStartChoiceCard
            icon={<Laptop size={20} />}
            title={t('quickStart.destination.agent', {
              machine: agent ? agentLabel(agent) : '',
            })}
            description={t('quickStart.destination.agentDesc')}
            selected
            onSelect={() => {}}
          />
        </Stack>
        <PathSelectorField
          label={t('quickStart.destination.pathLabel')}
          value={answers.destinationPath}
          onChange={(destinationPath) => onChange({ destinationPath })}
          placeholder="/srv/borg-backups/home"
          required
          error={inside}
          helperText={
            inside
              ? t('quickStart.destination.insideSource')
              : agent && !agentIsOnline(agent)
                ? t('quickStart.agent.offlineBrowse', { machine: agentLabel(agent) })
                : t('quickStart.destination.remotePathHint', {
                    machine: agent ? agentLabel(agent) : '',
                  })
          }
          browseButtonDisabled={!agentIsOnline(agent)}
          connectionType="agent"
          agentId={agent?.id}
          agentName={agent ? agentLabel(agent) : undefined}
          agentDefaultPath={agent?.default_path}
        />
        <Alert severity="info" variant="outlined">
          {t('quickStart.destination.offsiteTip')}
        </Alert>
      </Stack>
    )
  }

  return (
    <Stack spacing={2}>
      <Typography variant="h6" component="h3">
        {t('quickStart.destination.title')}
      </Typography>
      <Stack spacing={1.5} role="radiogroup" aria-label={t('quickStart.destination.title')}>
        <QuickStartChoiceCard
          icon={<HardDrive size={20} />}
          title={t('quickStart.destination.server')}
          description={t('quickStart.destination.serverDesc')}
          selected={!remote}
          onSelect={() => {
            if (!remote) return
            onChange({
              destinationKind: 'server',
              destinationConnectionId: '',
              destinationPath: suggestedDestinationPath(name),
            })
          }}
        />
        <QuickStartChoiceCard
          icon={<Server size={20} />}
          title={t('quickStart.destination.ssh')}
          description={t('quickStart.destination.sshDesc')}
          selected={remote}
          onSelect={() => {
            if (!remote) onChange({ destinationKind: 'ssh', destinationPath: '' })
          }}
        />
      </Stack>

      {remote && (
        <QuickStartSshConnect
          canAddMachine={canAddMachine}
          onBusyChange={onBusyChange}
          value={answers.destinationConnectionId}
          onChange={(destinationConnectionId) => {
            if (destinationConnectionId !== answers.destinationConnectionId) {
              onChange({ destinationConnectionId, destinationPath: '' })
            }
          }}
          label={t('quickStart.destination.sshLabel')}
        />
      )}

      {(!remote || connection) && (
        <PathSelectorField
          label={t('quickStart.destination.pathLabel')}
          value={answers.destinationPath}
          onChange={(destinationPath) => onChange({ destinationPath })}
          placeholder={remote ? '/srv/borg-backups/home' : '/local/borg-backups/home'}
          required
          error={inside}
          helperText={
            inside
              ? t('quickStart.destination.insideSource')
              : remote && connection
                ? t('quickStart.destination.remotePathHint', {
                    machine: `${connection.username}@${connection.host}`,
                  })
                : t('quickStart.destination.pathHint')
          }
          connectionType={remote ? 'ssh' : 'local'}
          sshConfig={remote ? sshBrowseConfig(connection) : undefined}
          initialPath={remote ? connection?.default_path || '/' : undefined}
          showSshMountPoints={false}
        />
      )}

      {!remote && (
        <Alert severity="info" variant="outlined">
          {t('quickStart.destination.offsiteTip')}
        </Alert>
      )}
    </Stack>
  )
}
