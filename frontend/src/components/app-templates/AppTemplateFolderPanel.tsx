import { useEffect } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  FormControlLabel,
  FormGroup,
  Link,
  Stack,
  Typography,
} from '@mui/material'
import { RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { AppTemplate } from '../../services/api'
import { mountHint, useAppDetection, type AppScanTarget } from './appTemplates'

interface AppTemplateFolderPanelProps {
  template: AppTemplate
  /** Null when the machine can't be scanned (agents); the panel then only explains where to look. */
  target: AppScanTarget | null
  root: string
  onUseRoot: (path: string) => void
  excludes: string[]
  onExcludesChange: (excludes: string[]) => void
}

/** Finds the app's folder on the chosen machine and lets the user skip what the app can rebuild. */
export default function AppTemplateFolderPanel({
  template,
  target,
  root,
  onUseRoot,
  excludes,
  onExcludesChange,
}: AppTemplateFolderPanelProps) {
  const { t } = useTranslation()
  const { detection, warning, scanning, rescan } = useAppDetection(template, target)
  const found = detection?.readable ? detection.path : null

  // Fill the folder in once when the app is found and nothing is picked yet.
  useEffect(() => {
    if (found && !root.trim()) onUseRoot(found)
  }, [found, root, onUseRoot])

  const rescanButton = (
    <Button
      size="small"
      color="inherit"
      startIcon={<RefreshCw size={14} />}
      onClick={rescan}
      disabled={scanning}
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
        <Alert severity="warning" variant="outlined" action={rescanButton}>
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
          action={
            root.trim() === detection.path ? undefined : (
              <Button size="small" color="inherit" onClick={() => onUseRoot(detection.path)}>
                {t('appTemplates.useFolder')}
              </Button>
            )
          }
        >
          {t('appTemplates.found', {
            app: template.name,
            container: detection.container_name,
            path: detection.path,
          })}
        </Alert>
      )
    }
    return (
      <Alert severity="info" variant="outlined" action={rescanButton}>
        {t('appTemplates.notFound', { app: template.name, hint: template.root_hint })}
        {warning && (
          <Typography variant="caption" component="p" sx={{ mt: 0.5 }}>
            {warning}
          </Typography>
        )}
      </Alert>
    )
  }

  const toggle = (path: string, checked: boolean) =>
    onExcludesChange(checked ? [...excludes, path] : excludes.filter((item) => item !== path))

  return (
    <Stack spacing={1.5}>
      {renderDetection()}
      {template.excludes.length > 0 && (
        <FormGroup aria-label={t('appTemplates.skipTitle')}>
          {template.excludes.map((exclude) => (
            <FormControlLabel
              key={exclude.path}
              control={
                <Checkbox
                  size="small"
                  checked={excludes.includes(exclude.path)}
                  onChange={(event) => toggle(exclude.path, event.target.checked)}
                />
              }
              label={
                <Typography variant="body2">
                  {exclude.label}{' '}
                  <Box component="code" sx={{ color: 'text.secondary', fontSize: '0.75rem' }}>
                    {exclude.path}/
                  </Box>
                </Typography>
              }
            />
          ))}
        </FormGroup>
      )}
      <Stack component="ul" spacing={0.5} sx={{ m: 0, pl: 2.5, color: 'text.secondary' }}>
        {template.notes.map((note) => (
          <Typography key={note} component="li" variant="caption">
            {note}
          </Typography>
        ))}
      </Stack>
      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
        {t('appTemplates.verified', { app: template.name, version: template.verified.app_version })}{' '}
        <Link href={template.docs_url} target="_blank" rel="noreferrer">
          {t('appTemplates.docs', { app: template.name })}
        </Link>
      </Typography>
    </Stack>
  )
}
