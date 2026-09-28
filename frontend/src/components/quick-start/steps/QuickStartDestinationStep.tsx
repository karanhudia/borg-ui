import { useEffect, useRef } from 'react'
import { Alert, Stack, Typography } from '@mui/material'
import { HardDrive, Server } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import PathSelectorField from '../../shared/PathSelectorField'
import QuickStartChoiceCard from '../QuickStartChoiceCard'
import QuickStartSshConnect from '../QuickStartSshConnect'
import { sshBrowseConfig, useSshConnection } from '../quickStartSsh'
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
}: QuickStartStepProps) {
  const { t } = useTranslation()
  const inside = destinationInsideSource(answers)
  const remote = answers.destinationKind === 'ssh'
  const connection = useSshConnection(remote ? answers.destinationConnectionId : '')
  const name = answers.name || 'backup'

  // Suggest a path once per chosen connection, after it has loaded: a machine
  // added in this step is not in the list until the refetch lands.
  const suggestedFor = useRef<number | null>(null)
  useEffect(() => {
    if (!connection || suggestedFor.current === connection.id) return
    suggestedFor.current = connection.id
    if (!answers.destinationPath) {
      onChange({ destinationPath: suggestedRemoteDestinationPath(name, connection) })
    }
  }, [connection, answers.destinationPath, name, onChange])

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
