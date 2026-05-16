import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { TFunction } from 'i18next'
import {
  Alert,
  Box,
  Button,
  ButtonBase,
  Chip,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Radio,
  RadioGroup,
  Select,
  Stack,
  TextField,
  Typography,
  alpha,
} from '@mui/material'
import { Container, Database, FileInput, FolderOpen } from 'lucide-react'

import ResponsiveDialog from '../../../components/ResponsiveDialog'
import { scriptsAPI, sourceDiscoveryAPI } from '../../../services/api'
import type { ScriptOption } from '../types'
import type {
  AppliedDatabaseSource,
  DatabaseDiscoveryResponse,
  DatabaseDiscoveryTarget,
} from './types'

type SourceType = 'paths' | 'database' | 'manual' | 'container'
type ScriptMode = 'create' | 'reuse' | 'skip'

interface SourceSelectionDialogProps {
  open: boolean
  scripts: ScriptOption[]
  loadingScripts: boolean
  onClose: () => void
  onUsePaths: () => void
  onApplyDatabase: (source: AppliedDatabaseSource) => void
  t: TFunction
}

const sourceTypeIcons = {
  paths: FolderOpen,
  database: Database,
  manual: FileInput,
  container: Container,
}

function sourceTypeLabel(type: SourceType, t: TFunction) {
  return t(`backupPlans.wizard.sourceSelection.sourceTypes.${type}`)
}

function sourceTypeDescription(type: SourceType, t: TFunction) {
  return t(`backupPlans.wizard.sourceSelection.sourceTypeDescriptions.${type}`)
}

function SourceTypeButton({
  type,
  disabled = false,
  onClick,
  t,
}: {
  type: SourceType
  disabled?: boolean
  onClick: () => void
  t: TFunction
}) {
  const Icon = sourceTypeIcons[type]

  return (
    <ButtonBase
      aria-label={sourceTypeLabel(type, t)}
      disabled={disabled}
      onClick={onClick}
      sx={{
        display: 'flex',
        alignItems: 'stretch',
        justifyContent: 'flex-start',
        gap: 2,
        width: '100%',
        p: 2,
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        textAlign: 'left',
        opacity: disabled ? 0.55 : 1,
        bgcolor: 'background.paper',
        transition: 'border-color 150ms ease, background-color 150ms ease',
        '&:hover': disabled
          ? {}
          : {
              borderColor: 'primary.main',
              bgcolor: (theme) => alpha(theme.palette.primary.main, 0.04),
            },
      }}
    >
      <Box
        sx={{
          width: 40,
          height: 40,
          borderRadius: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          bgcolor: 'action.hover',
          color: disabled ? 'text.disabled' : 'primary.main',
          flexShrink: 0,
        }}
      >
        <Icon size={20} />
      </Box>
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <Typography variant="subtitle2" fontWeight={700}>
            {sourceTypeLabel(type, t)}
          </Typography>
          {disabled && (
            <Chip size="small" label={t('backupPlans.wizard.sourceSelection.comingSoon')} />
          )}
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {sourceTypeDescription(type, t)}
        </Typography>
      </Box>
    </ButtonBase>
  )
}

function targetLabel(target: DatabaseDiscoveryTarget) {
  return target.status === 'detected' ? target.display_name : `${target.engine_label} template`
}

export function SourceSelectionDialog({
  open,
  scripts,
  loadingScripts,
  onClose,
  onUsePaths,
  onApplyDatabase,
  t,
}: SourceSelectionDialogProps) {
  const queryClient = useQueryClient()
  const [activeType, setActiveType] = useState<SourceType | null>(null)
  const [selectedTargetId, setSelectedTargetId] = useState('')
  const [scriptMode, setScriptMode] = useState<ScriptMode>('create')
  const [preScriptName, setPreScriptName] = useState('')
  const [postScriptName, setPostScriptName] = useState('')
  const [preScriptContent, setPreScriptContent] = useState('')
  const [postScriptContent, setPostScriptContent] = useState('')
  const [reusePreScriptId, setReusePreScriptId] = useState<number | ''>('')
  const [reusePostScriptId, setReusePostScriptId] = useState<number | ''>('')
  const [scriptError, setScriptError] = useState('')
  const [creatingScripts, setCreatingScripts] = useState(false)

  useEffect(() => {
    if (!open) {
      setActiveType(null)
      setSelectedTargetId('')
      setScriptMode('create')
      setScriptError('')
    }
  }, [open])

  const { data, isLoading, isError } = useQuery({
    queryKey: ['source-discovery', 'databases'],
    queryFn: async () => {
      const response = await sourceDiscoveryAPI.scanDatabases()
      return response.data as DatabaseDiscoveryResponse
    },
    enabled: open && activeType === 'database',
  })

  const databaseTargets = useMemo(
    () => [...(data?.databases || []), ...(data?.templates || [])],
    [data]
  )
  const selectedTarget =
    databaseTargets.find((target) => target.id === selectedTargetId) || databaseTargets[0]

  useEffect(() => {
    if (!selectedTarget && selectedTargetId) {
      setSelectedTargetId('')
    } else if (selectedTarget && !selectedTargetId) {
      setSelectedTargetId(selectedTarget.id)
    }
  }, [selectedTarget, selectedTargetId])

  useEffect(() => {
    if (!selectedTarget) return
    setPreScriptName(`${selectedTarget.script_name_base} pre`)
    setPostScriptName(`${selectedTarget.script_name_base} post`)
    setPreScriptContent(selectedTarget.pre_backup_script)
    setPostScriptContent(selectedTarget.post_backup_script)
    setScriptError('')
  }, [selectedTarget])

  const applyDisabled =
    creatingScripts ||
    !selectedTarget ||
    (scriptMode === 'create' && (!preScriptName.trim() || !postScriptName.trim())) ||
    (scriptMode === 'reuse' && (!reusePreScriptId || !reusePostScriptId))

  const handleApplyDatabase = async () => {
    if (!selectedTarget || applyDisabled) return
    setScriptError('')

    let preBackupScriptId: number | null = null
    let postBackupScriptId: number | null = null

    try {
      if (scriptMode === 'create') {
        setCreatingScripts(true)
        const [preResponse, postResponse] = await Promise.all([
          scriptsAPI.create({
            name: preScriptName.trim(),
            description: t('backupPlans.wizard.sourceSelection.generatedScriptDescription', {
              database: selectedTarget.display_name,
            }),
            content: preScriptContent,
            timeout: 300,
            run_on: 'always',
            category: 'custom',
          }),
          scriptsAPI.create({
            name: postScriptName.trim(),
            description: t('backupPlans.wizard.sourceSelection.generatedScriptDescription', {
              database: selectedTarget.display_name,
            }),
            content: postScriptContent,
            timeout: 300,
            run_on: 'always',
            category: 'custom',
          }),
        ])
        preBackupScriptId = Number(preResponse.data.id)
        postBackupScriptId = Number(postResponse.data.id)
        queryClient.invalidateQueries({ queryKey: ['scripts'] })
      } else if (scriptMode === 'reuse') {
        preBackupScriptId = Number(reusePreScriptId)
        postBackupScriptId = Number(reusePostScriptId)
      }

      onApplyDatabase({
        sourceType: 'local',
        sourceSshConnectionId: '',
        sourceDirectories: selectedTarget.source_directories,
        preBackupScriptId,
        postBackupScriptId,
        preBackupScriptParameters: {},
        postBackupScriptParameters: {},
      })
    } catch {
      setScriptError(t('backupPlans.wizard.sourceSelection.scriptCreateFailed'))
    } finally {
      setCreatingScripts(false)
    }
  }

  const footer = (
    <DialogActions>
      {activeType === 'database' && (
        <Button onClick={() => setActiveType(null)} disabled={creatingScripts}>
          {t('common.buttons.back')}
        </Button>
      )}
      <Button onClick={onClose} disabled={creatingScripts}>
        {t('common.buttons.cancel')}
      </Button>
      {activeType === 'database' && (
        <Button variant="contained" onClick={handleApplyDatabase} disabled={applyDisabled}>
          {t('backupPlans.wizard.sourceSelection.apply')}
        </Button>
      )}
    </DialogActions>
  )

  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="md" fullWidth footer={footer}>
      <DialogTitle sx={{ fontWeight: 700 }}>
        {t('backupPlans.wizard.sourceSelection.dialogTitle')}
      </DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pb: 2 }}>
        {!activeType && (
          <Stack spacing={1.5}>
            <SourceTypeButton type="paths" onClick={onUsePaths} t={t} />
            <SourceTypeButton type="database" onClick={() => setActiveType('database')} t={t} />
            <SourceTypeButton type="manual" onClick={onUsePaths} t={t} />
            <SourceTypeButton type="container" onClick={() => {}} disabled t={t} />
          </Stack>
        )}

        {activeType === 'database' && (
          <Stack spacing={2}>
            {isLoading && (
              <Alert severity="info">{t('backupPlans.wizard.sourceSelection.scanning')}</Alert>
            )}
            {isError && (
              <Alert severity="error">{t('backupPlans.wizard.sourceSelection.scanFailed')}</Alert>
            )}

            {databaseTargets.length > 0 && (
              <Stack spacing={1}>
                {databaseTargets.map((target) => (
                  <ButtonBase
                    key={target.id}
                    onClick={() => setSelectedTargetId(target.id)}
                    sx={{
                      p: 1.5,
                      border: 1,
                      borderColor: selectedTarget?.id === target.id ? 'primary.main' : 'divider',
                      borderRadius: 1,
                      textAlign: 'left',
                      display: 'block',
                      bgcolor:
                        selectedTarget?.id === target.id
                          ? (theme) => alpha(theme.palette.primary.main, 0.08)
                          : 'background.paper',
                    }}
                  >
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
                      <Typography variant="subtitle2" fontWeight={700}>
                        {targetLabel(target)}
                      </Typography>
                      <Chip
                        size="small"
                        label={
                          target.status === 'detected'
                            ? t('backupPlans.wizard.sourceSelection.detected')
                            : t('backupPlans.wizard.sourceSelection.template')
                        }
                        color={target.status === 'detected' ? 'success' : 'default'}
                      />
                    </Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                      {target.source_directories.join(', ')}
                    </Typography>
                  </ButtonBase>
                ))}
              </Stack>
            )}

            {selectedTarget && (
              <Stack spacing={2}>
                <Alert severity="info">
                  {t('backupPlans.wizard.sourceSelection.scriptsWillBeCreated')}
                </Alert>
                {selectedTarget.warnings.map((warning) => (
                  <Alert key={warning} severity="warning">
                    {warning}
                  </Alert>
                ))}

                <RadioGroup
                  value={scriptMode}
                  onChange={(event) => setScriptMode(event.target.value as ScriptMode)}
                >
                  <FormControlLabel
                    value="create"
                    control={<Radio />}
                    label={t('backupPlans.wizard.sourceSelection.scriptModeCreate')}
                  />
                  <FormControlLabel
                    value="reuse"
                    control={<Radio />}
                    label={t('backupPlans.wizard.sourceSelection.scriptModeReuse')}
                  />
                  <FormControlLabel
                    value="skip"
                    control={<Radio />}
                    label={t('backupPlans.wizard.sourceSelection.scriptModeSkip')}
                  />
                </RadioGroup>

                {scriptMode === 'create' && (
                  <Stack spacing={2}>
                    <TextField
                      label={t('backupPlans.wizard.sourceSelection.preScriptName')}
                      value={preScriptName}
                      onChange={(event) => setPreScriptName(event.target.value)}
                      fullWidth
                    />
                    <TextField
                      label={t('backupPlans.wizard.sourceSelection.preScriptContent')}
                      value={preScriptContent}
                      onChange={(event) => setPreScriptContent(event.target.value)}
                      multiline
                      minRows={4}
                      fullWidth
                    />
                    <TextField
                      label={t('backupPlans.wizard.sourceSelection.postScriptName')}
                      value={postScriptName}
                      onChange={(event) => setPostScriptName(event.target.value)}
                      fullWidth
                    />
                    <TextField
                      label={t('backupPlans.wizard.sourceSelection.postScriptContent')}
                      value={postScriptContent}
                      onChange={(event) => setPostScriptContent(event.target.value)}
                      multiline
                      minRows={4}
                      fullWidth
                    />
                  </Stack>
                )}

                {scriptMode === 'reuse' && (
                  <Stack spacing={2}>
                    <FormControl fullWidth disabled={loadingScripts}>
                      <InputLabel>
                        {t('backupPlans.wizard.sourceSelection.reusePreScript')}
                      </InputLabel>
                      <Select
                        value={reusePreScriptId}
                        label={t('backupPlans.wizard.sourceSelection.reusePreScript')}
                        onChange={(event) =>
                          setReusePreScriptId(event.target.value ? Number(event.target.value) : '')
                        }
                      >
                        {scripts.map((script) => (
                          <MenuItem key={script.id} value={script.id}>
                            {script.name}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    <FormControl fullWidth disabled={loadingScripts}>
                      <InputLabel>
                        {t('backupPlans.wizard.sourceSelection.reusePostScript')}
                      </InputLabel>
                      <Select
                        value={reusePostScriptId}
                        label={t('backupPlans.wizard.sourceSelection.reusePostScript')}
                        onChange={(event) =>
                          setReusePostScriptId(event.target.value ? Number(event.target.value) : '')
                        }
                      >
                        {scripts.map((script) => (
                          <MenuItem key={script.id} value={script.id}>
                            {script.name}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Stack>
                )}

                {scriptError && <Alert severity="error">{scriptError}</Alert>}
              </Stack>
            )}
          </Stack>
        )}
      </DialogContent>
    </ResponsiveDialog>
  )
}
