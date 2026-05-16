import { useState } from 'react'
import { Box, Button, Card, CardContent, Chip, Stack, TextField, Typography } from '@mui/material'
import { Database, Package } from 'lucide-react'

import ExcludePatternInput from '../../../components/ExcludePatternInput'
import { WizardStepDataSource } from '../../../components/wizard'
import { DatabaseDiscoveryDialog } from '../DatabaseDiscoveryDialog'
import type { DatabaseDiscoverySelection } from '../sourceDiscovery'
import type { BackupPlanWizardStepProps } from './types'

type SourceStepProps = Pick<
  BackupPlanWizardStepProps,
  | 'wizardState'
  | 'sshConnections'
  | 'updateState'
  | 'openSourceExplorer'
  | 'openExcludeExplorer'
  | 'onApplyDatabaseDiscovery'
  | 't'
>

export function SourceStep({
  wizardState,
  sshConnections,
  updateState,
  openSourceExplorer,
  openExcludeExplorer,
  onApplyDatabaseDiscovery,
  t,
}: SourceStepProps) {
  const [databaseDiscoveryOpen, setDatabaseDiscoveryOpen] = useState(false)

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
      <WizardStepDataSource
        repositoryLocation="local"
        repoSshConnectionId=""
        repositoryMode="full"
        data={{
          dataSource: wizardState.sourceType,
          sourceSshConnectionId: wizardState.sourceSshConnectionId,
          sourceDirs: wizardState.sourceDirectories,
        }}
        sshConnections={sshConnections}
        onChange={(updates) => {
          updateState({
            ...(updates.dataSource ? { sourceType: updates.dataSource } : {}),
            ...(updates.sourceSshConnectionId !== undefined
              ? { sourceSshConnectionId: updates.sourceSshConnectionId }
              : {}),
            ...(updates.sourceDirs !== undefined ? { sourceDirectories: updates.sourceDirs } : {}),
          })
        }}
        onBrowseSource={openSourceExplorer}
        onBrowseRemoteSource={openSourceExplorer}
      />
      <Box sx={{ border: 1, borderColor: 'divider', borderRadius: 2, p: 2 }}>
        <Stack spacing={2}>
          <Box>
            <Typography variant="subtitle2" fontWeight={700}>
              {t('backupPlans.wizard.sourceDiscovery.title', {
                defaultValue: 'Source discovery',
              })}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('backupPlans.wizard.sourceDiscovery.description', {
                defaultValue:
                  'Scan structured sources and generate backup-plan scripts without replacing manual path setup.',
              })}
            </Typography>
          </Box>

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
              gap: 2,
            }}
          >
            <Card variant="outlined" sx={{ bgcolor: 'background.default' }}>
              <CardContent>
                <Stack spacing={1.5}>
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <Box
                      sx={{
                        display: 'grid',
                        placeItems: 'center',
                        width: 38,
                        height: 38,
                        borderRadius: 2,
                        bgcolor: 'primary.main',
                        color: 'primary.contrastText',
                        flexShrink: 0,
                      }}
                    >
                      <Database size={20} />
                    </Box>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="subtitle2" fontWeight={700}>
                        {t('backupPlans.wizard.sourceDiscovery.databases.title', {
                          defaultValue: 'Databases',
                        })}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {t('backupPlans.wizard.sourceDiscovery.databases.description', {
                          defaultValue: 'Find supported database stores on this server.',
                        })}
                      </Typography>
                    </Box>
                  </Stack>
                  <Button
                    variant="outlined"
                    onClick={() => setDatabaseDiscoveryOpen(true)}
                    fullWidth
                  >
                    {t('backupPlans.wizard.sourceDiscovery.databases.action', {
                      defaultValue: 'Scan databases',
                    })}
                  </Button>
                </Stack>
              </CardContent>
            </Card>

            <Card variant="outlined" sx={{ bgcolor: 'background.default', opacity: 0.72 }}>
              <CardContent>
                <Stack spacing={1.5}>
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <Box
                      sx={{
                        display: 'grid',
                        placeItems: 'center',
                        width: 38,
                        height: 38,
                        borderRadius: 2,
                        bgcolor: 'action.hover',
                        color: 'text.secondary',
                        flexShrink: 0,
                      }}
                    >
                      <Package size={20} />
                    </Box>
                    <Box sx={{ minWidth: 0, flex: 1 }}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="subtitle2" fontWeight={700}>
                          {t('backupPlans.wizard.sourceDiscovery.containers.title', {
                            defaultValue: 'Containers',
                          })}
                        </Typography>
                        <Chip
                          size="small"
                          label={t('backupPlans.wizard.sourceDiscovery.containers.badge', {
                            defaultValue: 'Planned',
                          })}
                        />
                      </Stack>
                      <Typography variant="caption" color="text.secondary">
                        {t('backupPlans.wizard.sourceDiscovery.containers.description', {
                          defaultValue:
                            'Docker container scanning will use this same source workflow later.',
                        })}
                      </Typography>
                    </Box>
                  </Stack>
                  <Button variant="outlined" disabled fullWidth>
                    {t('backupPlans.wizard.sourceDiscovery.containers.action', {
                      defaultValue: 'Coming later',
                    })}
                  </Button>
                </Stack>
              </CardContent>
            </Card>
          </Box>
        </Stack>
      </Box>
      <ExcludePatternInput
        patterns={wizardState.excludePatterns}
        onChange={(excludePatterns) => updateState({ excludePatterns })}
        onBrowseClick={openExcludeExplorer}
      />
      <DatabaseDiscoveryDialog
        open={databaseDiscoveryOpen}
        onClose={() => setDatabaseDiscoveryOpen(false)}
        onApply={(selection: DatabaseDiscoverySelection) => onApplyDatabaseDiscovery(selection)}
        t={t}
      />
    </Stack>
  )
}
