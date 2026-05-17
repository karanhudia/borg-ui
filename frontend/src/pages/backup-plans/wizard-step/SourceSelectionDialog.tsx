import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Radio,
  RadioGroup,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import {
  ArrowLeft,
  Database as DatabaseIcon,
  FolderOpen,
  Info,
  Plus,
  Trash2,
  X,
} from 'lucide-react'
import type { TFunction } from 'i18next'

import CodeEditor from '../../../components/CodeEditor'
import FileExplorerDialog from '../../../components/FileExplorerDialog'
import ResponsiveDialog from '../../../components/ResponsiveDialog'
import {
  sourceDiscoveryAPI,
  type SourceDiscoveryDatabase,
  type SourceDiscoveryResponse,
  type SourceDiscoveryScriptDraft,
  type SourceDiscoveryTypeOption,
} from '../../../services/api'
import type { SourceLocation, SourceType } from '../../../types'
import type { ScriptOption, SSHConnection, WizardState } from '../types'
import type { SourceScriptCreateInput } from './types'

type SourceChoiceView = 'types' | 'paths' | 'database' | 'database-detail'
type ScriptMode = 'create' | 'reuse' | 'skip'
type SourceKey = 'local' | `remote:${number}`

interface SourceSelectionDialogProps {
  open: boolean
  wizardState: WizardState
  sshConnections: SSHConnection[]
  scripts: ScriptOption[]
  loadingScripts: boolean
  onClose: () => void
  updateState: (updates: Partial<WizardState>) => void
  onCreateScript: (input: SourceScriptCreateInput) => Promise<{ id: number }>
  t: TFunction
}

const fallbackSourceTypes: SourceDiscoveryTypeOption[] = [
  {
    id: 'paths',
    label: 'Files and folders',
    description: 'Back up local or remote paths.',
    status: 'enabled',
    disabled: false,
  },
  {
    id: 'database',
    label: 'Database',
    description: 'Scan supported databases or start from a template.',
    status: 'enabled',
    disabled: false,
  },
]

function sourceIcon(id: string) {
  if (id === 'database') return <DatabaseIcon size={18} />
  return <FolderOpen size={18} />
}

function scriptPayload(draft: SourceDiscoveryScriptDraft, name: string): SourceScriptCreateInput {
  return {
    name,
    description: draft.description,
    content: draft.content,
    timeout: draft.timeout,
    run_on: 'always',
    category: 'template',
  }
}

function cleanLocations(locations: SourceLocation[]): SourceLocation[] {
  return locations
    .map((location) => ({
      ...location,
      source_ssh_connection_id:
        location.source_type === 'remote' ? location.source_ssh_connection_id : null,
      paths: location.paths.map((path) => path.trim()).filter(Boolean),
    }))
    .filter((location) => location.paths.length > 0)
}

function locationsFromWizardState(wizardState: WizardState): SourceLocation[] {
  const existing = cleanLocations(wizardState.sourceLocations || [])
  if (existing.length > 0) return existing
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

function locationKey(location: SourceLocation): SourceKey {
  return location.source_type === 'remote' && location.source_ssh_connection_id
    ? `remote:${location.source_ssh_connection_id}`
    : 'local'
}

function locationForKey(
  sourceKey: SourceKey
): Pick<SourceLocation, 'source_type' | 'source_ssh_connection_id'> {
  if (sourceKey === 'local') {
    return { source_type: 'local', source_ssh_connection_id: null }
  }
  return { source_type: 'remote', source_ssh_connection_id: Number(sourceKey.split(':')[1]) }
}

function sourceTypeFromLocations(locations: SourceLocation[]): SourceType {
  if (locations.length === 0) return 'local'
  if (locations.length > 1) return 'mixed'
  return locations[0].source_type
}

function sourceConnectionFromLocations(locations: SourceLocation[]): number | '' {
  if (locations.length !== 1 || locations[0].source_type !== 'remote') return ''
  return locations[0].source_ssh_connection_id ? Number(locations[0].source_ssh_connection_id) : ''
}

function sourceLocationLabel(
  location: SourceLocation,
  sshConnections: SSHConnection[],
  t: TFunction
) {
  if (location.source_type === 'local') return t('backupPlans.sourceChooser.localSource')
  const connection = sshConnections.find((item) => item.id === location.source_ssh_connection_id)
  return connection
    ? `${connection.username}@${connection.host}`
    : t('backupPlans.wizard.review.connectionFallback', {
        id: location.source_ssh_connection_id,
      })
}

export function SourceSelectionDialog({
  open,
  wizardState,
  sshConnections,
  scripts,
  loadingScripts,
  onClose,
  updateState,
  onCreateScript,
  t,
}: SourceSelectionDialogProps) {
  const [view, setView] = useState<SourceChoiceView>('types')
  const [discovery, setDiscovery] = useState<SourceDiscoveryResponse | null>(null)
  const [loadingDiscovery, setLoadingDiscovery] = useState(false)
  const [discoveryError, setDiscoveryError] = useState(false)
  const [selectedDatabase, setSelectedDatabase] = useState<SourceDiscoveryDatabase | null>(null)
  const [scriptMode, setScriptMode] = useState<ScriptMode>('create')
  const [preScriptName, setPreScriptName] = useState('')
  const [postScriptName, setPostScriptName] = useState('')
  const [preScriptContent, setPreScriptContent] = useState('')
  const [postScriptContent, setPostScriptContent] = useState('')
  const [preExistingScriptId, setPreExistingScriptId] = useState<number | ''>('')
  const [postExistingScriptId, setPostExistingScriptId] = useState<number | ''>('')
  const [applying, setApplying] = useState(false)
  const [selectedSourceKey, setSelectedSourceKey] = useState<SourceKey>('local')
  const [sourcePath, setSourcePath] = useState('')
  const [draftSourceLocations, setDraftSourceLocations] = useState<SourceLocation[]>([])
  const [sourceExplorerOpen, setSourceExplorerOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    setView('types')
    const nextLocations = locationsFromWizardState(wizardState)
    setDraftSourceLocations(nextLocations)
    setSelectedSourceKey(nextLocations[0] ? locationKey(nextLocations[0]) : 'local')
    setSourcePath('')
    setSourceExplorerOpen(false)
    setSelectedDatabase(null)
    setScriptMode('create')
    setPreExistingScriptId(wizardState.preBackupScriptId || '')
    setPostExistingScriptId(wizardState.postBackupScriptId || '')
  }, [open, wizardState])

  useEffect(() => {
    if (!open || discovery) return

    let active = true
    setLoadingDiscovery(true)
    setDiscoveryError(false)
    sourceDiscoveryAPI
      .databases()
      .then((response) => {
        if (active) setDiscovery(response.data)
      })
      .catch(() => {
        if (active) setDiscoveryError(true)
      })
      .finally(() => {
        if (active) setLoadingDiscovery(false)
      })

    return () => {
      active = false
    }
  }, [discovery, open])

  const sourceTypes = discovery?.source_types?.length ? discovery.source_types : fallbackSourceTypes
  const visibleSourceTypes = sourceTypes.filter((sourceType) => sourceType.id !== 'container')
  const databaseItems = useMemo(() => {
    const detections = discovery?.detections || []
    const templates = discovery?.templates || []
    const detectedIds = new Set(detections.map((item) => item.id))
    return [...detections, ...templates.filter((item) => !detectedIds.has(item.id))]
  }, [discovery])

  const chooseDatabase = (database: SourceDiscoveryDatabase) => {
    setSelectedDatabase(database)
    setPreScriptName(database.script_drafts.pre_backup.name)
    setPostScriptName(database.script_drafts.post_backup.name)
    setPreScriptContent(database.script_drafts.pre_backup.content)
    setPostScriptContent(database.script_drafts.post_backup.content)
    setView('database-detail')
  }

  const applyDatabase = async () => {
    if (!selectedDatabase) return

    setApplying(true)
    try {
      let preBackupScriptId: number | null = null
      let postBackupScriptId: number | null = null

      if (scriptMode === 'create') {
        const preScript = await onCreateScript(
          scriptPayload(
            { ...selectedDatabase.script_drafts.pre_backup, content: preScriptContent },
            preScriptName.trim() || selectedDatabase.script_drafts.pre_backup.name
          )
        )
        const postScript = await onCreateScript(
          scriptPayload(
            { ...selectedDatabase.script_drafts.post_backup, content: postScriptContent },
            postScriptName.trim() || selectedDatabase.script_drafts.post_backup.name
          )
        )
        preBackupScriptId = preScript.id
        postBackupScriptId = postScript.id
      } else if (scriptMode === 'reuse') {
        preBackupScriptId = preExistingScriptId ? Number(preExistingScriptId) : null
        postBackupScriptId = postExistingScriptId ? Number(postExistingScriptId) : null
      }

      updateState({
        sourceType: 'local',
        sourceSshConnectionId: '',
        sourceDirectories: selectedDatabase.source_directories,
        sourceLocations: [
          {
            source_type: 'local',
            source_ssh_connection_id: null,
            paths: selectedDatabase.source_directories,
          },
        ],
        preBackupScriptId,
        postBackupScriptId,
        preBackupScriptParameters: {},
        postBackupScriptParameters: {},
      })
      onClose()
    } finally {
      setApplying(false)
    }
  }

  const addPathsToSelectedSource = (paths: string[]) => {
    const nextPaths = paths.map((path) => path.trim()).filter(Boolean)
    if (nextPaths.length === 0) return
    const locationBase = locationForKey(selectedSourceKey)

    setDraftSourceLocations((current) => {
      const existingIndex = current.findIndex(
        (location) => locationKey(location) === selectedSourceKey
      )
      if (existingIndex === -1) {
        return [
          ...current,
          {
            ...locationBase,
            paths: Array.from(new Set(nextPaths)),
          },
        ]
      }

      return current.map((location, index) => {
        if (index !== existingIndex) return location
        return {
          ...location,
          paths: Array.from(new Set([...location.paths, ...nextPaths])),
        }
      })
    })
  }

  const addSourcePath = () => {
    addPathsToSelectedSource([sourcePath])
    setSourcePath('')
  }

  const removeSourcePath = (sourceKey: SourceKey, path: string) => {
    setDraftSourceLocations((current) =>
      current
        .map((location) =>
          locationKey(location) === sourceKey
            ? { ...location, paths: location.paths.filter((item) => item !== path) }
            : location
        )
        .filter((location) => location.paths.length > 0)
    )
  }

  const removeSourceLocation = (sourceKey: SourceKey) => {
    setDraftSourceLocations((current) =>
      current.filter((location) => locationKey(location) !== sourceKey)
    )
  }

  const applyPaths = () => {
    const sourceLocations = cleanLocations(draftSourceLocations)
    updateState({
      sourceType: sourceTypeFromLocations(sourceLocations),
      sourceSshConnectionId: sourceConnectionFromLocations(sourceLocations),
      sourceDirectories: sourceLocations.flatMap((location) => location.paths),
      sourceLocations,
    })
    onClose()
  }

  const selectedSourceConnection =
    selectedSourceKey === 'local'
      ? null
      : sshConnections.find((connection) => selectedSourceKey === `remote:${connection.id}`) || null

  const selectedSourceExplorerSshConfig = selectedSourceConnection
    ? {
        ssh_key_id: selectedSourceConnection.ssh_key_id,
        host: selectedSourceConnection.host,
        username: selectedSourceConnection.username,
        port: selectedSourceConnection.port,
      }
    : undefined

  const renderTypeChooser = () => (
    <Stack spacing={1.25}>
      {visibleSourceTypes.map((sourceType) => (
        <Card
          key={sourceType.id}
          variant="outlined"
          sx={{
            borderColor: sourceType.disabled ? 'divider' : 'divider',
            bgcolor: sourceType.disabled ? 'action.hover' : 'background.paper',
            opacity: sourceType.disabled ? 0.72 : 1,
          }}
        >
          <CardActionArea
            component="button"
            disabled={sourceType.disabled}
            onClick={() => {
              if (sourceType.id === 'paths') setView('paths')
              if (sourceType.id === 'database') setView('database')
            }}
            sx={{ alignItems: 'stretch', textAlign: 'left', width: '100%' }}
          >
            <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
              <Stack direction="row" spacing={1.25} alignItems="flex-start">
                <Box
                  sx={{
                    alignItems: 'center',
                    bgcolor: 'action.hover',
                    borderRadius: 1,
                    color: 'text.secondary',
                    display: 'flex',
                    height: 32,
                    justifyContent: 'center',
                    width: 32,
                  }}
                >
                  {sourceIcon(sourceType.id)}
                </Box>
                <Box sx={{ minWidth: 0, flex: 1 }}>
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.25 }}>
                    <Typography variant="subtitle2">{sourceType.label}</Typography>
                    {sourceType.disabled && (
                      <Chip size="small" label={t('backupPlans.sourceChooser.containerPlanned')} />
                    )}
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    {sourceType.description}
                  </Typography>
                </Box>
              </Stack>
            </CardContent>
          </CardActionArea>
        </Card>
      ))}
    </Stack>
  )

  const renderPaths = () => (
    <Stack spacing={2}>
      <Button
        startIcon={<ArrowLeft size={16} />}
        onClick={() => setView('types')}
        size="small"
        sx={{ alignSelf: 'flex-start' }}
      >
        {t('backupPlans.sourceChooser.backToTypes')}
      </Button>
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
        <Button
          variant={selectedSourceKey === 'local' ? 'contained' : 'outlined'}
          onClick={() => setSelectedSourceKey('local')}
          size="small"
        >
          {t('backupPlans.sourceChooser.localSource')}
        </Button>
        {sshConnections.map((connection) => {
          const key: SourceKey = `remote:${connection.id}`
          return (
            <Button
              key={connection.id}
              variant={selectedSourceKey === key ? 'contained' : 'outlined'}
              onClick={() => setSelectedSourceKey(key)}
              size="small"
            >
              {`${connection.username}@${connection.host}`}
            </Button>
          )
        })}
      </Stack>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="stretch">
        <TextField
          label={t('backupPlans.sourceChooser.sourcePath')}
          value={sourcePath}
          onChange={(event) => setSourcePath(event.target.value)}
          size="small"
          fullWidth
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              addSourcePath()
            }
          }}
        />
        <Button
          variant="contained"
          startIcon={<Plus size={16} />}
          onClick={addSourcePath}
          disabled={!sourcePath.trim()}
          sx={{ flexShrink: 0 }}
        >
          {t('backupPlans.sourceChooser.addPath')}
        </Button>
        <Button
          variant="outlined"
          startIcon={<FolderOpen size={16} />}
          onClick={() => setSourceExplorerOpen(true)}
          sx={{ flexShrink: 0 }}
        >
          {t('backupPlans.sourceChooser.browseCurrentSource')}
        </Button>
      </Stack>
      <Box>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          {t('backupPlans.sourceChooser.selectedSourceGroups')}
        </Typography>
        {draftSourceLocations.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {t('backupPlans.sourceChooser.summaryEmpty')}
          </Typography>
        ) : (
          <Stack spacing={1}>
            {draftSourceLocations.map((location) => {
              const key = locationKey(location)
              return (
                <Paper key={key} variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                  <Stack spacing={1}>
                    <Stack
                      direction="row"
                      spacing={1}
                      alignItems="center"
                      justifyContent="space-between"
                    >
                      <Typography variant="subtitle2">
                        {sourceLocationLabel(location, sshConnections, t)}
                      </Typography>
                      <Tooltip title={t('backupPlans.sourceChooser.removeSourceGroup')}>
                        <IconButton
                          aria-label={t('backupPlans.sourceChooser.removeSourceGroup')}
                          onClick={() => removeSourceLocation(key)}
                          size="small"
                        >
                          <Trash2 size={16} />
                        </IconButton>
                      </Tooltip>
                    </Stack>
                    <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
                      {location.paths.map((path) => (
                        <Chip
                          key={path}
                          label={path}
                          size="small"
                          onDelete={() => removeSourcePath(key, path)}
                          deleteIcon={<X size={14} />}
                        />
                      ))}
                    </Stack>
                  </Stack>
                </Paper>
              )
            })}
          </Stack>
        )}
      </Box>
      <FileExplorerDialog
        key={`source-picker-${selectedSourceKey}`}
        open={sourceExplorerOpen}
        onClose={() => setSourceExplorerOpen(false)}
        onSelect={(paths) => {
          addPathsToSelectedSource(paths)
          setSourceExplorerOpen(false)
        }}
        title={t('backupPlans.wizard.fileExplorer.sourceTitle')}
        initialPath={selectedSourceConnection ? selectedSourceConnection.default_path || '/' : '/'}
        multiSelect
        connectionType={selectedSourceConnection ? 'ssh' : 'local'}
        sshConfig={selectedSourceExplorerSshConfig}
        selectMode="both"
        showSshMountPoints={false}
      />
    </Stack>
  )

  const renderDatabaseList = () => (
    <Stack spacing={1.25}>
      <Button
        startIcon={<ArrowLeft size={16} />}
        onClick={() => setView('types')}
        size="small"
        sx={{ alignSelf: 'flex-start' }}
      >
        {t('backupPlans.sourceChooser.backToTypes')}
      </Button>
      {loadingDiscovery && (
        <Typography variant="body2" color="text.secondary">
          {t('backupPlans.sourceChooser.loading')}
        </Typography>
      )}
      {discoveryError && (
        <Alert severity="warning">{t('backupPlans.sourceChooser.discoveryError')}</Alert>
      )}
      <Typography variant="subtitle2">
        {(discovery?.detections || []).length > 0
          ? t('backupPlans.sourceChooser.detectedDatabases')
          : t('backupPlans.sourceChooser.databaseTemplates')}
      </Typography>
      {databaseItems.length === 0 && !loadingDiscovery ? (
        <Typography variant="body2" color="text.secondary">
          {t('backupPlans.sourceChooser.noDatabaseTemplates')}
        </Typography>
      ) : (
        databaseItems.map((database) => (
          <Card key={database.id} variant="outlined">
            <CardActionArea
              component="button"
              onClick={() => chooseDatabase(database)}
              sx={{ alignItems: 'stretch', textAlign: 'left', width: '100%' }}
            >
              <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                <Stack spacing={0.75}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="subtitle2">{database.display_name}</Typography>
                    {database.detected && (
                      <Chip size="small" label={t('backupPlans.sourceChooser.detectedBadge')} />
                    )}
                  </Stack>
                  <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
                    <Chip size="small" label={database.engine} />
                    <Chip size="small" label={database.backup_strategy.replace(/_/g, ' ')} />
                    {database.client_commands.map((command) => (
                      <Chip key={command} size="small" label={command} variant="outlined" />
                    ))}
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    {database.source_directories.join(', ')}
                  </Typography>
                </Stack>
              </CardContent>
            </CardActionArea>
          </Card>
        ))
      )}
    </Stack>
  )

  const renderExistingScriptSelect = (
    label: string,
    value: number | '',
    onChange: (value: number | '') => void
  ) => (
    <FormControl fullWidth size="small" disabled={loadingScripts}>
      <InputLabel>{label}</InputLabel>
      <Select
        value={value}
        label={label}
        onChange={(event) => {
          const nextValue = event.target.value
          onChange(nextValue ? Number(nextValue) : '')
        }}
      >
        <MenuItem value="">
          <em>{t('scriptSelector.none')}</em>
        </MenuItem>
        {scripts.map((script) => (
          <MenuItem key={script.id} value={script.id} title={script.name}>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2" sx={{ overflowWrap: 'anywhere', whiteSpace: 'normal' }}>
                {script.name}
              </Typography>
            </Box>
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  )

  const renderDatabaseDetail = () => {
    if (!selectedDatabase) return null

    return (
      <Stack spacing={2}>
        <Button
          startIcon={<ArrowLeft size={16} />}
          onClick={() => setView('database')}
          size="small"
          sx={{ alignSelf: 'flex-start' }}
        >
          {t('backupPlans.sourceChooser.databaseTitle')}
        </Button>
        <Box>
          <Typography variant="subtitle1" fontWeight={600}>
            {selectedDatabase.display_name}
          </Typography>
          <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ mt: 0.75 }}>
            <Chip size="small" label={selectedDatabase.engine} />
            <Chip size="small" label={selectedDatabase.backup_strategy.replace(/_/g, ' ')} />
            <Tooltip title={selectedDatabase.notes.join(' ')}>
              <Chip
                size="small"
                icon={<Info size={14} />}
                label={t('backupPlans.sourceChooser.notesLabel')}
                variant="outlined"
              />
            </Tooltip>
          </Stack>
        </Box>
        <Box>
          <Typography variant="caption" color="text.secondary">
            {t('backupPlans.sourceChooser.sourcePaths')}
          </Typography>
          <Typography variant="body2" sx={{ fontFamily: 'monospace', mt: 0.25 }}>
            {selectedDatabase.source_directories.join(', ')}
          </Typography>
        </Box>
        <Divider />
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            {t('backupPlans.sourceChooser.scriptDrafts')}
          </Typography>
          <RadioGroup
            row
            value={scriptMode}
            onChange={(event) => setScriptMode(event.target.value as ScriptMode)}
          >
            <FormControlLabel
              value="create"
              control={<Radio size="small" />}
              label={t('backupPlans.sourceChooser.createScripts')}
            />
            <FormControlLabel
              value="reuse"
              control={<Radio size="small" />}
              label={t('backupPlans.sourceChooser.reuseScripts')}
            />
            <FormControlLabel
              value="skip"
              control={<Radio size="small" />}
              label={t('backupPlans.sourceChooser.skipScripts')}
            />
          </RadioGroup>
        </Box>
        {scriptMode === 'create' && (
          <Stack spacing={1.5}>
            <TextField
              label={t('backupPlans.sourceChooser.preScriptName')}
              value={preScriptName}
              onChange={(event) => setPreScriptName(event.target.value)}
              size="small"
              fullWidth
            />
            <CodeEditor
              label={t('backupPlans.sourceChooser.preScriptDraft')}
              value={preScriptContent}
              onChange={setPreScriptContent}
              height="180px"
              language="shell"
            />
            <TextField
              label={t('backupPlans.sourceChooser.postScriptName')}
              value={postScriptName}
              onChange={(event) => setPostScriptName(event.target.value)}
              size="small"
              fullWidth
            />
            <CodeEditor
              label={t('backupPlans.sourceChooser.postScriptDraft')}
              value={postScriptContent}
              onChange={setPostScriptContent}
              height="160px"
              language="shell"
            />
          </Stack>
        )}
        {scriptMode === 'reuse' && (
          <Stack spacing={1.5}>
            {renderExistingScriptSelect(
              t('backupPlans.sourceChooser.preExistingScript'),
              preExistingScriptId,
              setPreExistingScriptId
            )}
            {renderExistingScriptSelect(
              t('backupPlans.sourceChooser.postExistingScript'),
              postExistingScriptId,
              setPostExistingScriptId
            )}
          </Stack>
        )}
      </Stack>
    )
  }

  const content = (() => {
    if (view === 'paths') return renderPaths()
    if (view === 'database') return renderDatabaseList()
    if (view === 'database-detail') return renderDatabaseDetail()
    return renderTypeChooser()
  })()

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      footer={
        <DialogActions>
          <Button onClick={onClose}>{t('common.buttons.cancel')}</Button>
          {view === 'paths' && (
            <Button
              variant="contained"
              onClick={applyPaths}
              disabled={cleanLocations(draftSourceLocations).length === 0}
            >
              {t('backupPlans.sourceChooser.applyPaths')}
            </Button>
          )}
          {view === 'database-detail' && (
            <Button variant="contained" onClick={applyDatabase} disabled={applying}>
              {t('backupPlans.sourceChooser.applyDatabase')}
            </Button>
          )}
        </DialogActions>
      }
    >
      <DialogTitle sx={{ pb: 1 }}>{t('backupPlans.sourceChooser.title')}</DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        <Stack spacing={2}>{content}</Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}
