import { Box, Checkbox, FormControlLabel, Skeleton, Stack, Typography } from '@mui/material'
import { AlertTriangle, Database, Folder, RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type {
  AppExtraMount,
  AppFolderStats,
  AppTemplate,
  AppTemplateFolder,
} from '../../services/api'
import { formatBytes, formatRelativeTime } from '../../utils/dateUtils'
import { isStale } from './appTemplates'

interface AppFolderListProps {
  template: AppTemplate
  /** Folders the container mounts besides the app's own (external libraries). */
  extras: AppExtraMount[]
  includedExtras: string[]
  onIncludedExtrasChange: (paths: string[]) => void
  /** Who the check ran as, named when a folder can't be opened. */
  user: string | null
  /** Null while nothing is measured (no folder yet, or an agent). */
  stats: AppFolderStats[] | null
  measuring: boolean
  skipped: string[]
  onSkippedChange: (skipped: string[]) => void
}

function FolderIcon({ folder }: { folder: AppTemplateFolder }) {
  if (folder.role === 'database') return <Database size={18} />
  if (folder.role === 'rebuildable') return <RotateCcw size={18} />
  return <Folder size={18} />
}

/** What is inside the app's folder, in plain words, with sizes and what gets skipped. */
export default function AppFolderList({
  template,
  extras,
  includedExtras,
  onIncludedExtrasChange,
  user,
  stats,
  measuring,
  skipped,
  onSkippedChange,
}: AppFolderListProps) {
  const { t } = useTranslation()
  const statsFor = (path: string) => stats?.find((item) => item.path === path) ?? null

  // External folders read like the template's own, keyed by their absolute path.
  const extraRows: AppTemplateFolder[] = template.extra_mounts
    ? extras.map((extra) => ({
        path: extra.path,
        label: template.extra_mounts!.label,
        description: template.extra_mounts!.description,
        role: 'data',
        stale_after_hours: null,
      }))
    : []
  const isExtra = (path: string) => path.startsWith('/')
  const isSkipped = (path: string) =>
    isExtra(path) ? !includedExtras.includes(path) : skipped.includes(path)
  const rows = [...template.folders, ...extraRows]
  const kept = rows.filter((folder) => !isSkipped(folder.path))
  const keptSizes = kept.map((folder) => statsFor(folder.path)?.size_bytes)
  const total = keptSizes.reduce<number>((sum, size) => sum + (size ?? 0), 0)
  const unmeasured = keptSizes.some(
    (size, index) => size == null && statsFor(kept[index].path)?.exists !== false
  )

  const toggle = (path: string, skip: boolean) => {
    if (isExtra(path)) {
      onIncludedExtrasChange(
        skip ? includedExtras.filter((item) => item !== path) : [...includedExtras, path]
      )
    } else {
      onSkippedChange(skip ? [...skipped, path] : skipped.filter((item) => item !== path))
    }
  }

  const renderSize = (folder: AppTemplateFolder) => {
    if (measuring) return <Skeleton width={56} />
    const folderStats = statsFor(folder.path)
    if (!folderStats) return null
    if (!folderStats.exists) return t('appTemplates.folders.missing')
    if (!folderStats.readable) {
      return (
        <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', color: 'warning.main' }}>
          <AlertTriangle size={14} />
          <span>{t('appTemplates.folders.noAccess', { user: user ?? '?' })}</span>
        </Stack>
      )
    }
    if (folderStats.size_bytes == null) return t('appTemplates.folders.unmeasured')
    return formatBytes(folderStats.size_bytes)
  }

  // Every folder is the user's call: one "Back up" box per row, ticked unless
  // the app can rebuild it.
  const renderStatus = (folder: AppTemplateFolder) => {
    // Nothing to back up in a folder that isn't there.
    if (statsFor(folder.path)?.exists === false) return null
    return (
      <FormControlLabel
        sx={{ mr: 0 }}
        control={
          <Checkbox
            size="small"
            checked={!isSkipped(folder.path)}
            onChange={(event) => toggle(folder.path, !event.target.checked)}
          />
        }
        label={<Typography variant="body2">{t('appTemplates.folders.backUp')}</Typography>}
      />
    )
  }

  const renderDumpFreshness = (folder: AppTemplateFolder) => {
    // A dump the user chose not to back up needs no warning.
    if (folder.role !== 'database' || measuring || !stats || isSkipped(folder.path)) return null
    const folderStats = statsFor(folder.path)
    const latest = folderStats?.latest_modified_at ?? null
    if (!isStale(latest, folder.stale_after_hours)) {
      return (
        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
          {t('appTemplates.folders.latestDump', { when: formatRelativeTime(latest) })}
        </Typography>
      )
    }
    return (
      <Stack
        direction="row"
        spacing={0.5}
        sx={{ alignItems: 'center', color: 'warning.main' }}
        role="status"
      >
        <AlertTriangle size={14} />
        <Typography variant="caption">
          {latest
            ? t('appTemplates.folders.staleDump', {
                when: formatRelativeTime(latest),
                hours: folder.stale_after_hours,
              })
            : t('appTemplates.folders.noDump')}
        </Typography>
      </Stack>
    )
  }

  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2">{t('appTemplates.folders.title')}</Typography>
      <Stack
        component="ul"
        spacing={0}
        sx={{ m: 0, p: 0, listStyle: 'none', border: 1, borderColor: 'divider', borderRadius: 1.5 }}
      >
        {rows.map((folder, index) => {
          const skippedRow = isSkipped(folder.path)
          return (
            <Box
              component="li"
              key={folder.path}
              sx={{
                display: 'flex',
                gap: 1.5,
                alignItems: 'flex-start',
                px: 1.5,
                py: 1.25,
                borderTop: index === 0 ? 0 : 1,
                borderColor: 'divider',
                opacity: skippedRow ? 0.6 : 1,
              }}
            >
              <Box sx={{ color: 'text.secondary', pt: 0.25, flexShrink: 0 }}>
                <FolderIcon folder={folder} />
              </Box>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Stack
                  direction="row"
                  sx={{ alignItems: 'baseline', columnGap: 1, flexWrap: 'wrap', minWidth: 0 }}
                >
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {folder.label}
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{
                      fontFamily: 'monospace',
                      color: 'text.secondary',
                      overflowWrap: 'anywhere',
                    }}
                  >
                    {isExtra(folder.path) ? folder.path : `${folder.path}/`}
                  </Typography>
                </Stack>
                <Typography variant="caption" component="p" sx={{ color: 'text.secondary' }}>
                  {folder.description}
                </Typography>
                {renderDumpFreshness(folder)}
              </Box>
              <Stack spacing={0.25} sx={{ alignItems: 'flex-end', flexShrink: 0 }}>
                <Typography
                  variant="body2"
                  component="div"
                  sx={{ fontVariantNumeric: 'tabular-nums', color: 'text.secondary' }}
                >
                  {renderSize(folder)}
                </Typography>
                {renderStatus(folder)}
              </Stack>
            </Box>
          )
        })}
      </Stack>
      {stats && !measuring && (
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {t(unmeasured ? 'appTemplates.folders.totalAtLeast' : 'appTemplates.folders.total', {
            size: formatBytes(total),
          })}
        </Typography>
      )}
    </Stack>
  )
}
