import { useCallback, useState } from 'react'
import {
  Button,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material'
import type { TFunction } from 'i18next'

import AppTemplateFolderPanel from '../../../components/app-templates/AppTemplateFolderPanel'
import AppTemplateSelect from '../../../components/app-templates/AppTemplateSelect'
import {
  defaultAppExcludes,
  renderAppScript,
  useAppTemplates,
  type AppScanTarget,
} from '../../../components/app-templates/appTemplates'
import ResponsiveDialog from '../../../components/shared/ResponsiveDialog'
import PathSelectorField from '../../../components/shared/PathSelectorField'
import type { AppTemplate } from '../../../services/api'
import type { SSHConnection, WizardState } from '../types'
import { applyAppTemplate } from './appTemplateApply'
import type { SourceScriptCreateInput } from './types'

interface AppTemplateDialogProps {
  open: boolean
  onClose: () => void
  wizardState: WizardState
  sshConnections: SSHConnection[]
  updateState: (updates: Partial<WizardState>) => void
  onCreateScript: (input: SourceScriptCreateInput) => Promise<{ id: number }>
  t: TFunction
}

/** Adds a known app (its folder, excludes and pre-backup check) to the plan's sources. */
export function AppTemplateDialog({
  open,
  onClose,
  wizardState,
  sshConnections,
  updateState,
  onCreateScript,
  t,
}: AppTemplateDialogProps) {
  const { templates } = useAppTemplates()
  const [templateId, setTemplateId] = useState('')
  const [machine, setMachine] = useState<'local' | number>('local')
  const [root, setRoot] = useState('')
  const [extraPaths, setExtraPaths] = useState<string[]>([])
  const [excludes, setExcludes] = useState<string[]>([])
  const [applying, setApplying] = useState(false)

  const template: AppTemplate | null =
    templates.find((item) => item.id === templateId) ?? templates[0] ?? null
  const connection = machine === 'local' ? null : sshConnections.find((item) => item.id === machine)
  const target: AppScanTarget =
    machine === 'local'
      ? { source_type: 'local', source_ssh_connection_id: null }
      : { source_type: 'remote', source_ssh_connection_id: machine }

  const pickTemplate = (next: AppTemplate) => {
    setTemplateId(next.id)
    setExcludes(defaultAppExcludes(next))
    setRoot('')
  }
  // Defaults for the first template, before the user picks one.
  if (template && !templateId) pickTemplate(template)

  const setPaths = useCallback((nextRoot: string, nextExtras: string[]) => {
    setRoot(nextRoot)
    setExtraPaths(nextExtras)
  }, [])

  const apply = async () => {
    if (!template || !root.trim()) return
    setApplying(true)
    try {
      const content = machine === 'local' ? renderAppScript(template, root) : null
      const script =
        content && template.pre_backup_script
          ? await onCreateScript({
              name: `${template.pre_backup_script.name}: ${wizardState.name.trim() || template.name}`,
              description: template.pre_backup_script.description,
              content,
              timeout: template.pre_backup_script.timeout,
              run_on: 'always',
              category: 'template',
            })
          : null
      updateState(
        applyAppTemplate(wizardState, {
          template,
          sshConnectionId: machine === 'local' ? null : machine,
          root,
          extraPaths,
          excludes,
          scriptId: script?.id ?? null,
        })
      )
      setRoot('')
      onClose()
    } finally {
      setApplying(false)
    }
  }

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      footer={
        <DialogActions>
          <Button onClick={onClose} disabled={applying}>
            {t('common.buttons.cancel')}
          </Button>
          <Button variant="contained" onClick={apply} disabled={applying || !root.trim()}>
            {t('appTemplates.dialog.add')}
          </Button>
        </DialogActions>
      }
    >
      <DialogTitle>{t('appTemplates.dialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <AppTemplateSelect
            templates={templates}
            value={template}
            onChange={(next) => next && pickTemplate(next)}
          />
          <TextField
            select
            label={t('appTemplates.dialog.machine')}
            value={machine}
            onChange={(event) => {
              const value = event.target.value
              setMachine(value === 'local' ? 'local' : Number(value))
              setRoot('')
            }}
          >
            <MenuItem value="local">{t('appTemplates.dialog.thisServer')}</MenuItem>
            {sshConnections.map((item) => (
              <MenuItem key={item.id} value={item.id}>
                {item.username}@{item.host}
              </MenuItem>
            ))}
          </TextField>
          {template && (
            <AppTemplateFolderPanel
              template={template}
              target={target}
              root={root}
              extraPaths={extraPaths}
              onPathsChange={setPaths}
              excludes={excludes}
              onExcludesChange={setExcludes}
            />
          )}
          <PathSelectorField
            label={t('appTemplates.dialog.folder')}
            value={root}
            onChange={setRoot}
            placeholder={machine === 'local' ? '/local/srv/immich' : '/srv/immich'}
            connectionType={machine === 'local' ? 'local' : 'ssh'}
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
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}
