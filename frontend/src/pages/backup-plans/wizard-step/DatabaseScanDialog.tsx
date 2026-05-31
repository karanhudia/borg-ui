import { useEffect, useRef, useState } from 'react'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Skeleton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { ChevronDown, HardDrive, Info, Plus, RefreshCw, Server, Sliders, X } from 'lucide-react'
import type { TFunction } from 'i18next'

import DestinationSelect, {
  type DestinationOption,
} from '../../../components/shared/DestinationSelect'
import PathSelectorField from '../../../components/shared/PathSelectorField'
import ResponsiveDialog from '../../../components/shared/ResponsiveDialog'
import SshConnectionSelect from '../../../components/shared/SshConnectionSelect'
import {
  type DatabaseScanResponse,
  type SourceDiscoveryDatabase,
  sourceDiscoveryAPI,
} from '../../../services/api'
import type { SSHConnection } from '../types'
import { DatabaseBrandTile } from './DatabaseBrandTile'

export type ScanTargetState = { type: 'local' | 'remote'; sshId: number | '' }

type ScanErrorKind = 'ENDPOINT_MISSING' | 'OTHER'

interface ScanErrorState {
  kind: ScanErrorKind
  detail: string | null
}

const DEFAULT_DB_SCAN_PATHS = [
  '/var/lib/postgresql',
  '/var/lib/mysql',
  '/var/lib/mongodb',
  '/var/lib/redis',
]

// Match the server-side defaults in app/api/source_discovery.py. The dialog
// re-applies these on open so a user who tweaked them last time gets a clean
// slate, not a stale state.
const DEFAULT_SCAN_MAX_DEPTH = 6
const MIN_SCAN_MAX_DEPTH = 0
const MAX_SCAN_MAX_DEPTH = 10
const DEFAULT_SCAN_TIMEOUT_SECONDS = 30
const MIN_SCAN_TIMEOUT_SECONDS = 1
const MAX_SCAN_TIMEOUT_SECONDS = 300
const DEFAULT_SCAN_IGNORE_PATTERNS = [
  'node_modules',
  '.git',
  '.cache',
  'dist',
  'target',
  'build',
  '__pycache__',
  'overlay2',
]

function classifyScanError(err: unknown): ScanErrorState {
  if (err && typeof err === 'object' && 'response' in err) {
    const response = (err as { response?: { status?: number; data?: { detail?: string } } })
      .response
    if (response?.status === 404 || response?.status === 405) {
      return { kind: 'ENDPOINT_MISSING', detail: null }
    }
    if (response?.data?.detail) {
      return { kind: 'OTHER', detail: String(response.data.detail) }
    }
  }
  return { kind: 'OTHER', detail: null }
}

function resolveInitialScanTarget(
  initialScanTarget: ScanTargetState | undefined,
  sshConnections: SSHConnection[]
): ScanTargetState {
  if (initialScanTarget?.type !== 'remote') {
    return { type: 'local', sshId: '' }
  }
  const requestedId = initialScanTarget.sshId || sshConnections[0]?.id
  const resolvedId = sshConnections.some((connection) => connection.id === requestedId)
    ? requestedId
    : sshConnections[0]?.id
  return resolvedId ? { type: 'remote', sshId: resolvedId } : { type: 'local', sshId: '' }
}

export interface DatabaseScanChoice {
  database: SourceDiscoveryDatabase
  scanTarget: ScanTargetState
  scanTargetLabel: string | null
}

export interface DatabaseScanDialogProps {
  open: boolean
  onClose: () => void
  onChoose: (choice: DatabaseScanChoice) => void
  sshConnections: SSHConnection[]
  t: TFunction
  /** Override the initial scan target. Used by Storybook for specific states. */
  initialScanTarget?: ScanTargetState
}

export function DatabaseScanDialog({
  open,
  onClose,
  onChoose,
  sshConnections,
  t,
  initialScanTarget,
}: DatabaseScanDialogProps) {
  const [scanTarget, setScanTarget] = useState<ScanTargetState>(() =>
    resolveInitialScanTarget(initialScanTarget, sshConnections)
  )
  const [scanPaths, setScanPaths] = useState<string[]>(DEFAULT_DB_SCAN_PATHS)
  const [scanPathDraft, setScanPathDraft] = useState('')
  const [scanMaxDepth, setScanMaxDepth] = useState<number>(DEFAULT_SCAN_MAX_DEPTH)
  const [scanTimeoutSeconds, setScanTimeoutSeconds] = useState<number>(DEFAULT_SCAN_TIMEOUT_SECONDS)
  const [scanIgnorePatternsText, setScanIgnorePatternsText] = useState<string>(
    DEFAULT_SCAN_IGNORE_PATTERNS.join('\n')
  )
  const [scanResult, setScanResult] = useState<DatabaseScanResponse | null>(null)
  const [scanLoading, setScanLoading] = useState(false)
  const [scanError, setScanError] = useState<ScanErrorState | null>(null)
  const scanRequestId = useRef(0)

  useEffect(() => {
    if (!open) return
    setScanTarget(resolveInitialScanTarget(initialScanTarget, sshConnections))
    setScanPaths(DEFAULT_DB_SCAN_PATHS)
    setScanPathDraft('')
    setScanMaxDepth(DEFAULT_SCAN_MAX_DEPTH)
    setScanTimeoutSeconds(DEFAULT_SCAN_TIMEOUT_SECONDS)
    setScanIgnorePatternsText(DEFAULT_SCAN_IGNORE_PATTERNS.join('\n'))
    setScanResult(null)
    setScanError(null)
  }, [open, initialScanTarget, sshConnections])

  const runDatabaseScan = (immediate = false) => {
    if (!open) return
    if (scanTarget.type === 'remote' && !scanTarget.sshId) return
    if (scanPaths.length === 0) return

    const requestId = scanRequestId.current + 1
    scanRequestId.current = requestId
    const delay = immediate ? 0 : 300

    const handle = setTimeout(() => {
      setScanLoading(true)
      setScanError(null)
      sourceDiscoveryAPI
        .scanDatabases({
          source_type: scanTarget.type,
          source_ssh_connection_id: scanTarget.type === 'remote' ? Number(scanTarget.sshId) : null,
          paths: scanPaths,
          max_depth: scanMaxDepth,
          ignore_patterns: scanIgnorePatternsText
            .split('\n')
            .map((line) => line.trim())
            .filter((line) => line.length > 0),
          timeout_seconds: scanTimeoutSeconds,
        })
        .then((response) => {
          if (scanRequestId.current !== requestId) return
          setScanResult(response.data)
        })
        .catch((err) => {
          if (scanRequestId.current !== requestId) return
          setScanError(classifyScanError(err))
        })
        .finally(() => {
          if (scanRequestId.current !== requestId) return
          setScanLoading(false)
        })
    }, delay)

    return () => clearTimeout(handle)
  }

  // The first scan after open fires immediately; subsequent scans triggered by
  // user changes (target switch, path edit, advanced options) keep the 300ms
  // debounce to coalesce rapid input. Storybook captures rely on the initial
  // scan resolving before screenshot, which the debounce would otherwise miss.
  const initialScanDone = useRef(false)
  const scanPathsKey = scanPaths.join('|')
  useEffect(() => {
    if (!open) {
      initialScanDone.current = false
      return
    }
    const immediate = !initialScanDone.current
    const cleanup = runDatabaseScan(immediate)
    initialScanDone.current = true
    return cleanup
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    open,
    scanTarget.type,
    scanTarget.sshId,
    scanPathsKey,
    scanMaxDepth,
    scanTimeoutSeconds,
    scanIgnorePatternsText,
  ])

  const detections = scanResult?.detections || []
  const hasRemoteOptions = sshConnections.length > 0
  const remoteDisabled = scanTarget.type === 'remote' && !hasRemoteOptions
  const rootScanPathQueued = scanPaths.some((path) => path.trim() === '/')
  const scanCompleted = scanResult !== null
  const nothingFound = !scanLoading && !scanError && scanCompleted && detections.length === 0
  const awaitingFirstScan = !scanCompleted && !scanError
  const showSkeleton = scanLoading || awaitingFirstScan
  const targetLabel =
    scanResult?.scan_target.label ??
    (scanTarget.type === 'remote'
      ? t('backupPlans.sourceChooser.remoteMachine')
      : t('backupPlans.sourceChooser.borgUiServer'))
  const selectedScanConnection =
    scanTarget.type === 'remote' && scanTarget.sshId
      ? sshConnections.find((connection) => connection.id === scanTarget.sshId) || null
      : null
  const selectedScanSshConfig = selectedScanConnection
    ? {
        ssh_key_id: selectedScanConnection.ssh_key_id,
        host: selectedScanConnection.host,
        username: selectedScanConnection.username,
        port: selectedScanConnection.port,
      }
    : undefined

  const addScanPaths = (paths: string[]) => {
    const nextPaths = paths.map((path) => path.trim()).filter(Boolean)
    if (nextPaths.length === 0) {
      setScanPathDraft('')
      return
    }
    setScanPaths((current) => {
      const next = [...current]
      nextPaths.forEach((path) => {
        if (!next.includes(path)) next.push(path)
      })
      return next
    })
    setScanPathDraft('')
  }

  const addPath = () => {
    const next = scanPathDraft.trim()
    if (!next || scanPaths.includes(next)) {
      setScanPathDraft('')
      return
    }
    addScanPaths([next])
  }

  const removePath = (path: string) => {
    setScanPaths((current) => current.filter((item) => item !== path))
  }

  const scanTargetDestinations: DestinationOption[] = [
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
      description: hasRemoteOptions
        ? t('backupPlans.sourceChooser.remoteMachineDescription')
        : t('backupPlans.sourceChooser.noRemoteMachines'),
      disabled: !hasRemoteOptions,
    },
  ]

  const handleScanTargetChange = (key: string) => {
    if (key === 'local') {
      setScanTarget({ type: 'local', sshId: '' })
      return
    }
    if (key === 'remote') {
      if (!hasRemoteOptions) return
      const fallbackId =
        scanTarget.sshId && sshConnections.some((connection) => connection.id === scanTarget.sshId)
          ? scanTarget.sshId
          : sshConnections[0].id
      setScanTarget({ type: 'remote', sshId: fallbackId })
    }
  }

  const handleChoose = (database: SourceDiscoveryDatabase) => {
    onChoose({
      database,
      scanTarget,
      scanTargetLabel: scanResult?.scan_target.label ?? null,
    })
  }

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      // Match the parent SourceSelectionDialog height so the scan sub-modal
      // sits as a peer surface, not a smaller pop-up. DialogContent below
      // owns the internal scroll. Mobile uses auto height; ResponsiveDialog's
      // own 90vh cap governs the swipeable drawer.
      PaperProps={{ sx: { height: { xs: 'auto', md: 'min(860px, calc(100vh - 64px))' } } }}
    >
      <DialogTitle sx={{ pr: 6 }}>
        {t('backupPlans.sourceChooser.scanForDatabasesTitle')}
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {t('backupPlans.sourceChooser.scanForDatabasesSubtitle')}
        </Typography>
        <Tooltip title={t('backupPlans.sourceChooser.closeScanDialog')}>
          <IconButton
            aria-label={t('backupPlans.sourceChooser.closeScanDialog')}
            onClick={onClose}
            size="small"
            sx={{ position: 'absolute', top: 12, right: 12 }}
          >
            <X size={18} />
          </IconButton>
        </Tooltip>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <DestinationSelect
            value={scanTarget.type}
            onChange={handleScanTargetChange}
            destinations={scanTargetDestinations}
            label={t('backupPlans.sourceChooser.scanTarget')}
          />

          {scanTarget.type === 'remote' && hasRemoteOptions ? (
            <SshConnectionSelect
              value={scanTarget.sshId || ''}
              onChange={(id) => setScanTarget({ type: 'remote', sshId: id })}
              connections={sshConnections}
              label={t('backupPlans.sourceChooser.selectRemoteMachine')}
              emptyMessage={t('backupPlans.sourceChooser.noRemoteMachines')}
            />
          ) : (
            <Box
              sx={{
                border: 1,
                borderColor: 'divider',
                borderRadius: 1,
                bgcolor: 'action.hover',
                color: 'text.secondary',
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                px: 1.5,
                height: 56,
              }}
            >
              <HardDrive size={14} />
              <Typography variant="body2" color="text.secondary">
                {remoteDisabled
                  ? t('backupPlans.sourceChooser.noRemoteMachines')
                  : t('backupPlans.sourceChooser.readingFromLocal')}
              </Typography>
            </Box>
          )}

          <Stack spacing={1}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="flex-start">
              <PathSelectorField
                label={t('backupPlans.sourceChooser.sourcePath')}
                value={scanPathDraft}
                onChange={setScanPathDraft}
                placeholder="/path/to/scan"
                size="small"
                fullWidth
                disabled={remoteDisabled}
                initialPath={
                  selectedScanConnection ? selectedScanConnection.default_path || '/' : '/'
                }
                multiSelect
                selectMode="both"
                connectionType={selectedScanConnection ? 'ssh' : 'local'}
                sshConfig={selectedScanSshConfig}
                showSshMountPoints={false}
                onSelectPaths={addScanPaths}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    addPath()
                  }
                }}
              />
              <Button
                variant="contained"
                startIcon={<Plus size={16} />}
                onClick={addPath}
                disabled={!scanPathDraft.trim() || remoteDisabled}
                sx={{ flexShrink: 0 }}
              >
                {t('backupPlans.sourceChooser.addPath')}
              </Button>
            </Stack>

            <Box>
              <Stack
                direction="row"
                spacing={1}
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 1 }}
              >
                <Typography variant="subtitle2">
                  {t('backupPlans.sourceChooser.pathsToScan')}
                </Typography>
                <Button
                  size="small"
                  variant="text"
                  startIcon={
                    scanLoading ? (
                      <CircularProgress size={12} color="inherit" />
                    ) : (
                      <RefreshCw size={14} />
                    )
                  }
                  onClick={() => runDatabaseScan(true)}
                  disabled={scanLoading || remoteDisabled || scanPaths.length === 0}
                  sx={{ textTransform: 'none', fontWeight: 500 }}
                >
                  {scanLoading
                    ? t('backupPlans.sourceChooser.scanning')
                    : t('backupPlans.sourceChooser.rescan')}
                </Button>
              </Stack>
              <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
                {scanPaths.map((path) => (
                  <Chip
                    key={path}
                    size="small"
                    label={path}
                    onDelete={() => removePath(path)}
                    deleteIcon={<X size={14} />}
                    sx={{
                      fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace',
                      fontSize: '0.75rem',
                    }}
                  />
                ))}
                {scanPaths.length === 0 && (
                  <Typography variant="caption" color="text.secondary">
                    {t('backupPlans.sourceChooser.noScanPaths')}
                  </Typography>
                )}
              </Stack>
              {!rootScanPathQueued && !remoteDisabled && (
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={{ xs: 0.5, sm: 0.75 }}
                  alignItems={{ xs: 'flex-start', sm: 'center' }}
                  sx={{ mt: 0.75, color: 'text.secondary' }}
                >
                  <Stack direction="row" spacing={0.5} alignItems="center" sx={{ minWidth: 0 }}>
                    <Info size={13} />
                    <Typography variant="caption" color="text.secondary">
                      {t('backupPlans.sourceChooser.rootScanSuggestion')}
                    </Typography>
                  </Stack>
                  <Button
                    size="small"
                    variant="text"
                    onClick={() => addScanPaths(['/'])}
                    sx={{
                      minWidth: 0,
                      p: 0,
                      lineHeight: 1.4,
                      textTransform: 'none',
                      fontWeight: 500,
                      '&:hover': { bgcolor: 'transparent', textDecoration: 'underline' },
                    }}
                  >
                    {t('backupPlans.sourceChooser.addRootScanPath')}
                  </Button>
                </Stack>
              )}
            </Box>

            {/* Advanced scan options: collapsed by default; users who need to
                scan deeper, skip more directories, or extend the timeout open
                this section. Defaults are sensible for a homelab box. */}
            <Accordion
              disableGutters
              elevation={0}
              sx={{
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 1,
                bgcolor: 'transparent',
                '&:before': { display: 'none' },
              }}
            >
              <AccordionSummary
                expandIcon={<ChevronDown size={16} />}
                sx={{ minHeight: 40, '& .MuiAccordionSummary-content': { my: 0.75 } }}
              >
                <Stack direction="row" spacing={1} alignItems="center">
                  <Sliders size={14} />
                  <Typography variant="subtitle2">
                    {t('backupPlans.sourceChooser.advancedScanOptions')}
                  </Typography>
                </Stack>
              </AccordionSummary>
              <AccordionDetails sx={{ pt: 0 }}>
                <Stack spacing={2}>
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                    <TextField
                      label={t('backupPlans.sourceChooser.scanMaxDepth')}
                      helperText={t('backupPlans.sourceChooser.scanMaxDepthHelp')}
                      type="number"
                      size="small"
                      fullWidth
                      value={scanMaxDepth}
                      onChange={(e) => {
                        const next = Number(e.target.value)
                        if (Number.isNaN(next)) return
                        setScanMaxDepth(
                          Math.max(MIN_SCAN_MAX_DEPTH, Math.min(MAX_SCAN_MAX_DEPTH, next))
                        )
                      }}
                      slotProps={{
                        htmlInput: {
                          min: MIN_SCAN_MAX_DEPTH,
                          max: MAX_SCAN_MAX_DEPTH,
                          step: 1,
                        },
                      }}
                      disabled={remoteDisabled}
                    />
                    <TextField
                      label={t('backupPlans.sourceChooser.scanTimeout')}
                      helperText={t('backupPlans.sourceChooser.scanTimeoutHelp')}
                      type="number"
                      size="small"
                      fullWidth
                      value={scanTimeoutSeconds}
                      onChange={(e) => {
                        const next = Number(e.target.value)
                        if (Number.isNaN(next)) return
                        setScanTimeoutSeconds(
                          Math.max(
                            MIN_SCAN_TIMEOUT_SECONDS,
                            Math.min(MAX_SCAN_TIMEOUT_SECONDS, next)
                          )
                        )
                      }}
                      slotProps={{
                        htmlInput: {
                          min: MIN_SCAN_TIMEOUT_SECONDS,
                          max: MAX_SCAN_TIMEOUT_SECONDS,
                          step: 1,
                        },
                      }}
                      disabled={remoteDisabled}
                    />
                  </Stack>
                  <TextField
                    label={t('backupPlans.sourceChooser.scanIgnorePatterns')}
                    helperText={t('backupPlans.sourceChooser.scanIgnorePatternsHelp')}
                    multiline
                    minRows={3}
                    maxRows={8}
                    size="small"
                    fullWidth
                    value={scanIgnorePatternsText}
                    onChange={(e) => setScanIgnorePatternsText(e.target.value)}
                    slotProps={{
                      htmlInput: {
                        style: {
                          fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace',
                          fontSize: '0.8125rem',
                        },
                      },
                    }}
                    disabled={remoteDisabled}
                  />
                </Stack>
              </AccordionDetails>
            </Accordion>
          </Stack>

          {showSkeleton && (
            <>
              <Skeleton
                variant="rounded"
                height={56}
                sx={{ borderRadius: 1 }}
                animation={scanLoading ? 'wave' : 'pulse'}
              />
              <Box
                sx={{
                  display: 'grid',
                  gap: 1.25,
                  p: 0.75,
                  mx: -0.75,
                  gridTemplateColumns: {
                    xs: 'repeat(2, minmax(0, 1fr))',
                    sm: 'repeat(3, minmax(0, 1fr))',
                    md: 'repeat(4, minmax(0, 1fr))',
                  },
                }}
              >
                {Array.from({ length: 4 }).map((_, index) => (
                  <Skeleton
                    key={index}
                    variant="rounded"
                    height={64}
                    sx={{ borderRadius: 1 }}
                    animation={scanLoading ? 'wave' : 'pulse'}
                  />
                ))}
              </Box>
            </>
          )}

          {!showSkeleton && scanResult && scanResult.warnings.length > 0 && (
            <Alert severity="warning">
              <Stack spacing={0.25}>
                {scanResult.warnings.map((warning, index) => (
                  <Typography key={`${warning.code}-${index}`} variant="caption">
                    {warning.path ? `${warning.path}: ` : ''}
                    {warning.message}
                  </Typography>
                ))}
              </Stack>
            </Alert>
          )}

          {!showSkeleton && scanError?.kind === 'ENDPOINT_MISSING' && (
            <Alert severity="info">{t('backupPlans.sourceChooser.scanEndpointMissing')}</Alert>
          )}

          {!showSkeleton && scanError?.kind === 'OTHER' && (
            <Alert
              severity="warning"
              action={
                <Button
                  color="inherit"
                  size="small"
                  onClick={() => runDatabaseScan(true)}
                  disabled={scanLoading}
                >
                  {t('backupPlans.sourceChooser.rescan')}
                </Button>
              }
            >
              <Stack spacing={0.25}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {t('backupPlans.sourceChooser.scanFailedTitle', { target: targetLabel })}
                </Typography>
                <Typography variant="caption">
                  {scanError.detail ?? t('backupPlans.sourceChooser.scanFailedBody')}
                </Typography>
              </Stack>
            </Alert>
          )}

          {!showSkeleton && nothingFound && (
            <Alert severity="info">
              <Stack spacing={0.5}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {t('backupPlans.sourceChooser.nothingFoundTitle', { target: targetLabel })}
                </Typography>
                {scanResult && scanResult.scanned_paths.length > 0 && (
                  <Stack
                    direction="row"
                    spacing={0.5}
                    useFlexGap
                    flexWrap="wrap"
                    alignItems="baseline"
                  >
                    <Typography variant="caption" sx={{ flexShrink: 0 }}>
                      {t('backupPlans.sourceChooser.checkedPaths')}
                    </Typography>
                    {scanResult.scanned_paths.map((path, index) => (
                      <Typography
                        key={path}
                        component="span"
                        variant="caption"
                        sx={{
                          fontFamily:
                            'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
                        }}
                      >
                        {path}
                        {index < scanResult.scanned_paths.length - 1 ? ',' : ''}
                      </Typography>
                    ))}
                  </Stack>
                )}
                <Typography variant="caption">
                  {t('backupPlans.sourceChooser.nothingFoundBody')}
                </Typography>
              </Stack>
            </Alert>
          )}

          {!showSkeleton && detections.length > 0 && (
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                {t('backupPlans.sourceChooser.detectedSection')}
              </Typography>
              <Box
                sx={{
                  display: 'grid',
                  gap: 1.25,
                  p: 0.75,
                  mx: -0.75,
                  gridTemplateColumns: {
                    xs: 'repeat(2, minmax(0, 1fr))',
                    sm: 'repeat(3, minmax(0, 1fr))',
                    md: 'repeat(4, minmax(0, 1fr))',
                  },
                }}
              >
                {detections.map((database) => (
                  <DatabaseBrandTile
                    key={database.id}
                    database={database}
                    detectedLabel={t('backupPlans.sourceChooser.detectedBadge')}
                    onClick={() => handleChoose(database)}
                  />
                ))}
              </Box>
            </Box>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.buttons.cancel')}</Button>
      </DialogActions>
    </ResponsiveDialog>
  )
}
