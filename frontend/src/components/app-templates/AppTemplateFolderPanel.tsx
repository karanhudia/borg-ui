import { useEffect, useMemo } from 'react'
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  CircularProgress,
  Link,
  Stack,
  Typography,
} from '@mui/material'
import { Info, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { AppTemplate } from '../../services/api'
import AppFolderList from './AppFolderList'
import AppLogo from './AppLogo'
import {
  mountHint,
  readAccessCommands,
  useAppDetection,
  useAppInspection,
  type AppScanTarget,
} from './appTemplates'

interface AppTemplateFolderPanelProps {
  template: AppTemplate
  /** Null when the machine can't be scanned (agents); the panel then only explains where to look. */
  target: AppScanTarget | null
  /** The app's folder. */
  root: string
  /** Whether the app's folder is part of the backup; its rows show unticked when not. */
  rootIncluded: boolean
  onRootIncludedChange: (included: boolean) => void
  /** External folders (libraries) the user keeps in the backup. */
  extraPaths: string[]
  onPathsChange: (root: string, extraPaths: string[]) => void
  /** The detected container's name ('' when not found), for scripts that run inside it. */
  onContainerChange: (container: string) => void
  excludes: string[]
  onExcludesChange: (excludes: string[]) => void
}

// Alert actions sit at the top by default; center them against multi-line messages.
const alertSx = { '& .MuiAlert-action': { alignItems: 'center', pt: 0, pl: 2 } }
const actionSx = { whiteSpace: 'nowrap', flexShrink: 0 }

/** Finds the app's folder on the chosen machine and shows what is in it: sizes, dump age, what is skipped. */
export default function AppTemplateFolderPanel({
  template,
  target,
  root,
  rootIncluded,
  onRootIncludedChange,
  extraPaths,
  onPathsChange,
  onContainerChange,
  excludes,
  onExcludesChange,
}: AppTemplateFolderPanelProps) {
  const { t } = useTranslation()
  const { detection, warning, scanning, rescan } = useAppDetection(template, target)
  const unreadable = Boolean(detection && !detection.readable)
  // Only folders Borg UI can reach; one not mounted into its container is no use.
  const detectedExtras = useMemo(
    () => (detection?.extra_mounts ?? []).filter((extra) => extra.readable),
    [detection]
  )
  const detectedExtraPaths = useMemo(
    () => detectedExtras.map((extra) => extra.path),
    [detectedExtras]
  )
  const { stats, rootStatus, user, measuring } = useAppInspection(
    template,
    unreadable ? null : target,
    root,
    detectedExtraPaths
  )
  const found = detection?.readable ? detection.path : null

  // Fill the folders in once when the app is found and nothing is picked yet.
  useEffect(() => {
    if (found && !root.trim()) onPathsChange(found, detectedExtraPaths)
  }, [found, root, detectedExtraPaths, onPathsChange])

  const container = detection?.container_name ?? ''
  useEffect(() => onContainerChange(container), [container, onContainerChange])

  const rescanButton = (
    <Button
      size="small"
      color="inherit"
      startIcon={<RefreshCw size={14} />}
      onClick={rescan}
      disabled={scanning}
      sx={actionSx}
    >
      {t('appTemplates.scanAgain')}
    </Button>
  )

  const renderDetection = () => {
    if (!target) {
      return (
        <Alert severity="info" variant="outlined">
          {t('appTemplates.pickManually', { app: template.name, hint: template.root_hint })}
        </Alert>
      )
    }
    if (scanning) {
      return (
        <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }} role="status">
          <CircularProgress size={16} />
          <Typography variant="body2">
            {t('appTemplates.scanning', { app: template.name })}
          </Typography>
        </Stack>
      )
    }
    if (detection && !detection.readable) {
      return (
        <Alert severity="warning" variant="outlined" action={rescanButton} sx={alertSx}>
          <Typography variant="body2">
            {t('appTemplates.notReadable', { app: template.name, path: detection.host_path })}
          </Typography>
          <Box
            component="code"
            sx={{ display: 'block', mt: 1, fontFamily: 'monospace', fontSize: '0.8rem' }}
          >
            {mountHint(detection.host_path)}
          </Box>
        </Alert>
      )
    }
    if (detection) {
      return (
        <Alert
          severity="success"
          variant="outlined"
          icon={<AppLogo app={template} size={22} />}
          sx={alertSx}
          action={
            root.trim() === detection.path ? undefined : (
              <Button
                size="small"
                color="inherit"
                onClick={() => onPathsChange(detection.path, detectedExtraPaths)}
                sx={actionSx}
              >
                {t('appTemplates.useFolder')}
              </Button>
            )
          }
        >
          <AlertTitle sx={{ mb: 0.25 }}>
            {t('appTemplates.found', { app: template.name, container: detection.container_name })}
          </AlertTitle>
          <Box
            component="code"
            sx={{ fontFamily: 'monospace', fontSize: '0.75rem', overflowWrap: 'anywhere' }}
          >
            {detection.path}
          </Box>
        </Alert>
      )
    }
    return (
      <Alert severity="info" variant="outlined" action={rescanButton} sx={alertSx}>
        {t('appTemplates.notFound', { app: template.name, hint: template.root_hint })}
        {warning && (
          <Typography variant="caption" component="p" sx={{ mt: 0.5 }}>
            {warning}
          </Typography>
        )}
      </Alert>
    )
  }

  return (
    <Stack spacing={1.5}>
      {renderDetection()}
      {rootStatus === 'denied' && (
        <Alert severity="warning" variant="outlined" role="alert">
          <AlertTitle>
            {t('appTemplates.denied.title', { path: root.trim(), user: user ?? '?' })}
          </AlertTitle>
          <Typography variant="body2" sx={{ mb: 1 }}>
            {t('appTemplates.denied.why')}
          </Typography>
          <Typography variant="body2">
            {t('appTemplates.denied.fixFolder', {
              hint: template.root_hint,
              app: template.name,
              id: template.id,
            })}
          </Typography>
          <Typography variant="body2" sx={{ mt: 1 }}>
            {t('appTemplates.denied.fixAcl', { user: user ?? '?' })}
          </Typography>
          <Box
            component="pre"
            sx={{
              m: 0,
              mt: 0.5,
              fontFamily: 'monospace',
              fontSize: '0.75rem',
              whiteSpace: 'pre-wrap',
              overflowWrap: 'anywhere',
            }}
          >
            {readAccessCommands(user ?? 'USER', root)}
          </Box>
        </Alert>
      )}
      {rootStatus === 'missing' && (
        <Alert severity="warning" variant="outlined" role="alert">
          {t('appTemplates.missingRoot', {
            path: root.trim(),
            hint: template.root_hint,
            app: template.name,
          })}
        </Alert>
      )}
      <AppFolderList
        template={template}
        appFolderIncluded={rootIncluded}
        onAppFolderIncludedChange={onRootIncludedChange}
        extras={detectedExtras}
        includedExtras={extraPaths}
        onIncludedExtrasChange={(paths) => onPathsChange(root, paths)}
        user={user}
        stats={stats}
        measuring={measuring}
        skipped={excludes}
        onSkippedChange={onExcludesChange}
      />
      <Alert severity="info" variant="outlined" icon={<Info size={20} />}>
        <AlertTitle>{t('appTemplates.goodToKnow')}</AlertTitle>
        <Stack spacing={0.75}>
          {template.notes.map((note) => (
            <Typography key={note} variant="body2">
              {note}
            </Typography>
          ))}
        </Stack>
        <Typography variant="caption" component="p" sx={{ mt: 1, color: 'text.secondary' }}>
          {t('appTemplates.verified', {
            app: template.name,
            version: template.verified.app_version,
          })}{' '}
          <Link href={template.docs_url} target="_blank" rel="noreferrer">
            {t('appTemplates.docs', { app: template.name })}
          </Link>
        </Typography>
      </Alert>
    </Stack>
  )
}
