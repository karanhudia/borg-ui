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
  LinearProgress,
  Stack,
  TextField,
  Typography,
  alpha,
} from '@mui/material'
import { Database, RefreshCw } from 'lucide-react'
import type { TFunction } from 'i18next'

import ResponsiveDialog from '../../components/ResponsiveDialog'
import {
  sourceDiscoveryAPI,
  type SourceDiscoveryDatabase,
  type SourceDiscoveryResponse,
} from '../../services/api'
import type { DatabaseDiscoverySelection } from './sourceDiscovery'

interface DatabaseDiscoveryDialogProps {
  open: boolean
  onClose: () => void
  onApply: (selection: DatabaseDiscoverySelection) => Promise<void> | void
  t: TFunction
}

function confidenceColor(confidence: SourceDiscoveryDatabase['confidence']) {
  if (confidence === 'high') return 'success'
  if (confidence === 'medium') return 'warning'
  return 'default'
}

function candidateGroupLabel(candidate: SourceDiscoveryDatabase, t: TFunction) {
  if (candidate.discovery_source === 'template') {
    return t('backupPlans.wizard.sourceDiscovery.dialog.template', {
      defaultValue: 'Template',
    })
  }
  return t('backupPlans.wizard.sourceDiscovery.dialog.detected', {
    defaultValue: 'Detected',
  })
}

export function DatabaseDiscoveryDialog({
  open,
  onClose,
  onApply,
  t,
}: DatabaseDiscoveryDialogProps) {
  const [data, setData] = useState<SourceDiscoveryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [sourcePath, setSourcePath] = useState('')
  const [preScriptContent, setPreScriptContent] = useState('')
  const [postScriptContent, setPostScriptContent] = useState('')
  const [applying, setApplying] = useState(false)

  const candidates = useMemo(() => {
    if (!data) return []
    return [...data.databases, ...data.templates]
  }, [data])

  const selected = candidates.find((candidate) => candidate.id === selectedId) || null

  const loadDatabases = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await sourceDiscoveryAPI.scanDatabases()
      setData(response.data)
      const firstCandidate = response.data.databases[0] || response.data.templates[0] || null
      if (firstCandidate) {
        setSelectedId(firstCandidate.id)
        setSourcePath(firstCandidate.source_directories[0] || '')
        setPreScriptContent(firstCandidate.pre_backup_script.content)
        setPostScriptContent(firstCandidate.post_backup_script.content)
      }
    } catch {
      setError(
        t('backupPlans.wizard.sourceDiscovery.dialog.scanFailed', {
          defaultValue: 'Database scan failed. Try again or use manual paths.',
        })
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!open) {
      setData(null)
      setSelectedId(null)
      setSourcePath('')
      setPreScriptContent('')
      setPostScriptContent('')
      setError(null)
      setApplying(false)
      return
    }

    void loadDatabases()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const selectCandidate = (candidate: SourceDiscoveryDatabase) => {
    setSelectedId(candidate.id)
    setSourcePath(candidate.source_directories[0] || '')
    setPreScriptContent(candidate.pre_backup_script.content)
    setPostScriptContent(candidate.post_backup_script.content)
    setError(null)
  }

  const sourceDirectories = sourcePath.trim() ? [sourcePath.trim()] : []
  const canApply =
    Boolean(selected) &&
    sourceDirectories.length > 0 &&
    preScriptContent.trim().length > 0 &&
    postScriptContent.trim().length > 0 &&
    !applying

  const applySelection = async () => {
    if (!selected || !canApply) return
    setApplying(true)
    setError(null)
    try {
      await onApply({
        database: selected,
        sourceDirectories,
        preBackupScript: {
          ...selected.pre_backup_script,
          content: preScriptContent,
        },
        postBackupScript: {
          ...selected.post_backup_script,
          content: postScriptContent,
        },
      })
      onClose()
    } catch {
      setError(
        t('backupPlans.wizard.sourceDiscovery.applyFailed', {
          defaultValue: 'Failed to apply database source',
        })
      )
    } finally {
      setApplying(false)
    }
  }

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      footer={
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button onClick={onClose} disabled={applying}>
            {t('common.buttons.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button variant="contained" onClick={applySelection} disabled={!canApply}>
            {applying
              ? t('backupPlans.wizard.sourceDiscovery.dialog.applying', {
                  defaultValue: 'Applying...',
                })
              : t('backupPlans.wizard.sourceDiscovery.dialog.apply', {
                  defaultValue: 'Use database source',
                })}
          </Button>
        </DialogActions>
      }
    >
      <DialogTitle sx={{ pb: 1 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" gap={2}>
          <Box>
            <Typography variant="h6" fontWeight={700}>
              {t('backupPlans.wizard.sourceDiscovery.dialog.title', {
                defaultValue: 'Database discovery',
              })}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('backupPlans.wizard.sourceDiscovery.dialog.description', {
                defaultValue:
                  'Scan local database stores and generate editable plan scripts for consistent filesystem backups.',
              })}
            </Typography>
          </Box>
          <Button
            startIcon={<RefreshCw size={16} />}
            onClick={loadDatabases}
            disabled={loading || applying}
          >
            {t('backupPlans.wizard.sourceDiscovery.dialog.rescan', {
              defaultValue: 'Rescan',
            })}
          </Button>
        </Stack>
      </DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        <Stack spacing={2}>
          {loading && <LinearProgress />}
          {error && <Alert severity="error">{error}</Alert>}
          {data && data.databases.length === 0 && (
            <Alert severity="info">
              {t('backupPlans.wizard.sourceDiscovery.dialog.noDetected', {
                defaultValue:
                  'No running supported databases were detected. Start from a supported template and verify the path before saving.',
              })}
            </Alert>
          )}

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', md: 'minmax(260px, 0.85fr) 1.4fr' },
              gap: 2,
              minHeight: { md: 500 },
            }}
          >
            <Stack spacing={1.5}>
              {candidates.map((candidate) => {
                const selectedCandidate = candidate.id === selectedId
                return (
                  <Card
                    key={candidate.id}
                    variant="outlined"
                    sx={{
                      borderColor: selectedCandidate ? 'primary.main' : 'divider',
                      bgcolor: selectedCandidate
                        ? (theme) => alpha(theme.palette.primary.main, 0.08)
                        : 'background.paper',
                    }}
                  >
                    <CardActionArea onClick={() => selectCandidate(candidate)}>
                      <CardContent>
                        <Stack direction="row" spacing={1.5} alignItems="flex-start">
                          <Box
                            sx={{
                              display: 'grid',
                              placeItems: 'center',
                              width: 38,
                              height: 38,
                              borderRadius: 2,
                              bgcolor: selectedCandidate ? 'primary.main' : 'action.hover',
                              color: selectedCandidate ? 'primary.contrastText' : 'text.secondary',
                              flexShrink: 0,
                            }}
                          >
                            <Database size={20} />
                          </Box>
                          <Box sx={{ minWidth: 0, flex: 1 }}>
                            <Typography variant="subtitle2" fontWeight={700}>
                              {candidate.name}
                            </Typography>
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              sx={{
                                display: 'block',
                                overflowWrap: 'anywhere',
                              }}
                            >
                              {candidate.source_directories[0]}
                            </Typography>
                            <Stack direction="row" spacing={0.75} sx={{ mt: 1, flexWrap: 'wrap' }}>
                              <Chip
                                size="small"
                                label={candidateGroupLabel(candidate, t)}
                                variant="outlined"
                              />
                              <Chip
                                size="small"
                                label={candidate.confidence}
                                color={confidenceColor(candidate.confidence)}
                                variant="outlined"
                              />
                            </Stack>
                          </Box>
                        </Stack>
                      </CardContent>
                    </CardActionArea>
                  </Card>
                )
              })}
            </Stack>

            <Box sx={{ border: 1, borderColor: 'divider', borderRadius: 2, p: 2 }}>
              {selected ? (
                <Stack spacing={2}>
                  <Box>
                    <Typography variant="subtitle1" fontWeight={700}>
                      {selected.engine_label}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t('backupPlans.wizard.sourceDiscovery.dialog.strategy', {
                        defaultValue:
                          'Borg will back up the database files while generated plan scripts stop and start the service.',
                      })}
                    </Typography>
                  </Box>

                  <TextField
                    label={t('backupPlans.wizard.sourceDiscovery.dialog.sourcePath', {
                      defaultValue: 'Database source path',
                    })}
                    value={sourcePath}
                    onChange={(event) => setSourcePath(event.target.value)}
                    fullWidth
                    required
                  />

                  <Divider />

                  <TextField
                    label={t('backupPlans.wizard.sourceDiscovery.dialog.preScript', {
                      defaultValue: 'Pre-backup script',
                    })}
                    value={preScriptContent}
                    onChange={(event) => setPreScriptContent(event.target.value)}
                    multiline
                    minRows={7}
                    fullWidth
                    required
                    InputProps={{
                      sx: { fontFamily: 'monospace', fontSize: '0.875rem' },
                    }}
                  />

                  <TextField
                    label={t('backupPlans.wizard.sourceDiscovery.dialog.postScript', {
                      defaultValue: 'Post-backup script',
                    })}
                    value={postScriptContent}
                    onChange={(event) => setPostScriptContent(event.target.value)}
                    multiline
                    minRows={7}
                    fullWidth
                    required
                    InputProps={{
                      sx: { fontFamily: 'monospace', fontSize: '0.875rem' },
                    }}
                  />

                  <Alert severity="warning">
                    {t('backupPlans.wizard.sourceDiscovery.dialog.reviewWarning', {
                      defaultValue:
                        'Stopping a database pauses writes while the plan runs. Review paths, service names, and maintenance windows before enabling a schedule.',
                    })}
                  </Alert>
                </Stack>
              ) : (
                <Box
                  sx={{
                    minHeight: 240,
                    display: 'grid',
                    placeItems: 'center',
                    textAlign: 'center',
                    color: 'text.secondary',
                  }}
                >
                  <Typography variant="body2">
                    {t('backupPlans.wizard.sourceDiscovery.dialog.selectDatabase', {
                      defaultValue: 'Select a database to review generated scripts.',
                    })}
                  </Typography>
                </Box>
              )}
            </Box>
          </Box>
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}
