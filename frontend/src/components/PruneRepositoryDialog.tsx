import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  DialogTitle,
  DialogContent,
  DialogActions,
  Box,
  Typography,
  Button,
  Stack,
  CircularProgress,
  Chip,
  Tooltip,
  InputBase,
  alpha,
  useTheme,
} from '@mui/material'
import ResponsiveDialog from './ResponsiveDialog'
import {
  Scissors,
  FlaskConical,
  TriangleAlert,
  Info,
  Clock,
  Sun,
  CalendarDays,
  CalendarRange,
  Calendar,
  CheckCircle2,
  XCircle,
  Terminal,
} from 'lucide-react'
import { Repository } from '../types'

interface PruneForm {
  keep_hourly: number
  keep_daily: number
  keep_weekly: number
  keep_monthly: number
  keep_quarterly: number
  keep_yearly: number
}

interface PruneResults {
  dry_run: boolean
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  prune_result?: any
}

interface PruneRepositoryDialogProps {
  open: boolean
  repository: Repository | null
  onClose: () => void
  onDryRun: (form: PruneForm) => Promise<void>
  onConfirmPrune: (form: PruneForm) => Promise<void>
  isLoading: boolean
  results: PruneResults | null
  initialForm?: Partial<PruneForm>
}

const defaultPruneForm: PruneForm = {
  keep_hourly: 0,
  keep_daily: 7,
  keep_weekly: 4,
  keep_monthly: 6,
  keep_quarterly: 0,
  keep_yearly: 1,
}

type IntlListFormatConstructor = new (
  locale: string,
  options: { style: 'long'; type: 'conjunction' }
) => {
  format: (items: string[]) => string
}

const formatRetentionList = (items: string[], locale: string) => {
  if (items.length === 0) return ''
  const ListFormat =
    typeof Intl !== 'undefined'
      ? (Intl as typeof Intl & { ListFormat?: IntlListFormatConstructor }).ListFormat
      : undefined
  if (ListFormat) {
    return new ListFormat(locale, { style: 'long', type: 'conjunction' }).format(items)
  }
  if (items.length === 1) return items[0]
  if (items.length === 2) return `${items[0]} and ${items[1]}`
  return `${items.slice(0, -1).join(', ')}, and ${items[items.length - 1]}`
}

// ─── Colorized terminal output ────────────────────────────────────────────────

type BorgLineType =
  | 'keep'
  | 'prune'
  | 'separator'
  | 'stats-header'
  | 'stats-deleted'
  | 'stats-all'
  | 'stats-chunk'
  | 'empty'
  | 'normal'

// V1 prune logs are stored as "[stderr] {...json...}" lines — extract the message
function extractMessage(raw: string): string {
  const prefixMatch = raw.match(/^\[(stderr|stdout)\] (.+)$/)
  if (prefixMatch) {
    try {
      const parsed = JSON.parse(prefixMatch[2])
      return typeof parsed.message === 'string' ? parsed.message : prefixMatch[2]
    } catch {
      return prefixMatch[2]
    }
  }
  return raw
}

function classifyLine(msg: string): BorgLineType {
  const t = msg.trim()
  if (t === '') return 'empty'
  if (msg.startsWith('Keeping archive') || msg.startsWith('Would keep archive')) return 'keep'
  if (
    msg.startsWith('Pruning archive') ||
    msg.startsWith('Would prune archive') ||
    msg.startsWith('Would prune:')
  )
    return 'prune'
  if (/^-{6,}/.test(t)) return 'separator'
  if (/^\s*Deleted data:/.test(msg)) return 'stats-deleted'
  if (/^\s*All archives:/.test(msg)) return 'stats-all'
  if (/^\s*Chunk index:/.test(msg)) return 'stats-chunk'
  if (/^\s*(Original size|Compressed size|Unique chunks|Total chunks)/.test(msg))
    return 'stats-header'
  return 'normal'
}

// Segment a "Keeping/Pruning archive ..." line into typed spans
function segmentArchiveLine(line: string) {
  // Pattern: <Verb> archive <rule?>: <spaces><name> <date> [<hash>]
  const ruleMatch = line.match(/(\(rule:[^)]+\))/)
  const hashMatch = line.match(/\[([a-f0-9]{16,})\]/)
  const colonIdx = line.indexOf(':')

  if (colonIdx === -1) return [{ text: line, kind: 'verb' as const }]

  const prefix = line.slice(0, colonIdx + 1) // "Keeping archive (rule: ...): "
  const rest = line.slice(colonIdx + 1) // "   archive-name date [hash]"

  const segments: { text: string; kind: 'verb' | 'rule' | 'name' | 'date' | 'hash' | 'plain' }[] =
    []

  if (ruleMatch) {
    const rIdx = prefix.indexOf(ruleMatch[1])
    segments.push({ text: prefix.slice(0, rIdx), kind: 'verb' })
    segments.push({ text: ruleMatch[1], kind: 'rule' })
    segments.push({ text: prefix.slice(rIdx + ruleMatch[1].length), kind: 'plain' })
  } else {
    segments.push({ text: prefix, kind: 'verb' })
  }

  if (hashMatch) {
    const hStart = rest.lastIndexOf('[' + hashMatch[1])
    const beforeHash = rest.slice(0, hStart).trimEnd()
    // Split beforeHash into name + date (last word-group is date-like)
    const dateMatch = beforeHash.match(/\s+((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+\S+\s+\S+)$/)
    if (dateMatch) {
      segments.push({
        text: ' ' + beforeHash.slice(0, beforeHash.length - dateMatch[0].length).trim(),
        kind: 'name',
      })
      segments.push({ text: ' ' + dateMatch[1], kind: 'date' })
    } else {
      segments.push({ text: ' ' + beforeHash.trim(), kind: 'name' })
    }
    segments.push({ text: ' [' + hashMatch[1] + ']', kind: 'hash' })
  } else {
    segments.push({ text: rest, kind: 'name' })
  }

  return segments
}

interface ColorizedOutputProps {
  text: string
  isFailed?: boolean
}

function ColorizedOutput({ text, isFailed = false }: ColorizedOutputProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const lines = text.split('\n').map(extractMessage)

  const colorMap: Record<BorgLineType, string | undefined> = {
    keep: isDark ? theme.palette.success.light : theme.palette.success.dark,
    prune: isDark ? theme.palette.error.light : theme.palette.error.dark,
    separator: isDark ? alpha('#fff', 0.2) : alpha('#000', 0.25),
    'stats-deleted': isDark ? theme.palette.error.light : theme.palette.error.dark,
    'stats-all': isDark ? alpha('#fff', 0.85) : alpha('#000', 0.82),
    'stats-chunk': isDark ? alpha('#fff', 0.45) : alpha('#000', 0.45),
    'stats-header': isDark ? alpha('#fff', 0.45) : alpha('#000', 0.45),
    empty: undefined,
    normal: isFailed
      ? isDark
        ? theme.palette.error.light
        : theme.palette.error.dark
      : isDark
        ? alpha('#fff', 0.82)
        : alpha('#000', 0.78),
  }

  const spanColor = {
    verb: (type: 'keep' | 'prune') =>
      type === 'keep'
        ? isDark
          ? theme.palette.success.light
          : theme.palette.success.dark
        : isDark
          ? theme.palette.error.light
          : theme.palette.error.dark,
    rule: isDark ? theme.palette.warning.light : '#b45309',
    name: isDark ? alpha('#fff', 0.82) : alpha('#000', 0.82),
    date: isDark ? alpha('#fff', 0.45) : alpha('#000', 0.42),
    hash: isDark ? alpha('#fff', 0.25) : alpha('#000', 0.28),
    plain: isDark ? alpha('#fff', 0.55) : alpha('#000', 0.55),
  }

  return (
    <Box
      sx={{
        m: 0,
        p: 2,
        fontSize: '0.745rem',
        lineHeight: 1.7,
        overflow: 'auto',
        maxHeight: 380,
        fontFamily: 'ui-monospace, "Cascadia Code", "Fira Code", monospace',
      }}
    >
      {lines.map((line, i) => {
        const type = classifyLine(line)

        if (type === 'empty') {
          return <Box key={i} component="div" sx={{ height: '0.5em' }} />
        }

        if (type === 'keep' || type === 'prune') {
          const segs = segmentArchiveLine(line)
          return (
            <Box key={i} component="div" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
              {segs.map((seg, j) => {
                const color =
                  seg.kind === 'verb'
                    ? spanColor.verb(type)
                    : seg.kind === 'rule'
                      ? spanColor.rule
                      : seg.kind === 'name'
                        ? spanColor.name
                        : seg.kind === 'date'
                          ? spanColor.date
                          : seg.kind === 'hash'
                            ? spanColor.hash
                            : spanColor.plain
                const fontWeight = seg.kind === 'verb' ? 700 : seg.kind === 'rule' ? 600 : 400
                return (
                  <Box key={j} component="span" sx={{ color, fontWeight }}>
                    {seg.text}
                  </Box>
                )
              })}
            </Box>
          )
        }

        return (
          <Box
            key={i}
            component="div"
            sx={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
              color: colorMap[type],
              fontWeight: type === 'stats-deleted' || type === 'stats-all' ? 500 : 400,
            }}
          >
            {line}
          </Box>
        )
      })}
    </Box>
  )
}

// ─── Results Dialog ───────────────────────────────────────────────────────────

interface PruneResultsDialogProps {
  open: boolean
  results: PruneResults
  repository: Repository | null
  currentForm: PruneForm
  isLoading: boolean
  onClose: () => void
  onRunPrune: (form: PruneForm) => void
  onCloseAll: () => void
}

function PruneResultsDialog({
  open,
  results,
  repository,
  currentForm,
  isLoading,
  onClose,
  onRunPrune,
  onCloseAll,
}: PruneResultsDialogProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const isFailed = results.prune_result?.success === false
  const isDryRun = results.dry_run
  const stdout = results.prune_result?.stdout ?? ''
  const stderr = results.prune_result?.stderr ?? ''
  const hasOutput = stdout || stderr

  const borderColor = isDark ? alpha('#fff', 0.08) : alpha('#000', 0.09)
  const terminalBg = isDark ? alpha('#000', 0.45) : alpha('#000', 0.035)

  // Determine header appearance
  const headerIcon = isFailed ? (
    <XCircle size={20} />
  ) : isDryRun ? (
    <FlaskConical size={20} />
  ) : (
    <CheckCircle2 size={20} />
  )

  const headerColor = isFailed
    ? theme.palette.error.main
    : isDryRun
      ? theme.palette.warning.main
      : theme.palette.success.main

  const headerBg = alpha(headerColor, isDark ? 0.18 : 0.1)

  const badge = isFailed
    ? t('dialogs.prune.pruneFailedBadge')
    : isDryRun
      ? t('dialogs.prune.dryRunPreviewBadge')
      : t('dialogs.prune.pruneCompleteBadge')

  const badgeColor = isFailed ? 'error' : isDryRun ? 'warning' : 'success'

  const title = isDryRun
    ? t('dialogs.prune.dryRunResultsTitle')
    : isFailed
      ? t('dialogs.prune.operationFailed')
      : t('dialogs.prune.pruneResultsTitle')

  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      {/* ── Title ── */}
      <DialogTitle sx={{ pb: 1.5 }}>
        <Stack direction="row" spacing={1.5} alignItems="flex-start">
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 38,
              height: 38,
              borderRadius: 1.5,
              bgcolor: headerBg,
              color: headerColor,
              flexShrink: 0,
            }}
          >
            {headerIcon}
          </Box>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap">
              <Typography variant="h6" fontWeight={600} lineHeight={1.3}>
                {title}
              </Typography>
              <Chip
                label={badge}
                color={badgeColor}
                size="small"
                sx={{
                  height: 18,
                  fontSize: '0.6rem',
                  fontWeight: 700,
                  letterSpacing: '0.06em',
                  '.MuiChip-label': { px: 1 },
                }}
              />
            </Stack>
            {repository?.name && (
              <Typography
                variant="body2"
                color="text.secondary"
                noWrap
                sx={{ fontFamily: 'ui-monospace, monospace', fontSize: '0.72rem', mt: 0.25 }}
              >
                {repository.name}
              </Typography>
            )}
          </Box>
        </Stack>
      </DialogTitle>

      {/* ── Output ── */}
      <DialogContent sx={{ pt: 0 }}>
        {hasOutput ? (
          <Box
            sx={{
              border: '1px solid',
              borderColor,
              borderRadius: 1.5,
              overflow: 'hidden',
              bgcolor: terminalBg,
            }}
          >
            {/* Terminal header bar */}
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                px: 1.5,
                py: 0.75,
                borderBottom: '1px solid',
                borderColor,
                bgcolor: isDark ? alpha('#fff', 0.03) : alpha('#000', 0.03),
              }}
            >
              <Box sx={{ color: 'text.disabled', display: 'flex' }}>
                <Terminal size={13} />
              </Box>
              <Typography
                variant="caption"
                sx={{
                  fontWeight: 700,
                  fontSize: '0.6rem',
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  color: 'text.disabled',
                }}
              >
                {t('dialogs.prune.outputLabel')}
              </Typography>
            </Box>

            {/* stdout */}
            {stdout && <ColorizedOutput text={stdout} />}

            {/* stderr — shown as a distinct section when present alongside stdout */}
            {stderr && (
              <Box
                sx={{
                  borderTop: stdout ? '1px solid' : 'none',
                  borderColor,
                }}
              >
                {stdout && (
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1,
                      px: 1.5,
                      py: 0.75,
                      borderBottom: '1px solid',
                      borderColor: isFailed
                        ? alpha(theme.palette.error.main, 0.2)
                        : alpha(theme.palette.warning.main, 0.2),
                    }}
                  >
                    <Typography
                      variant="caption"
                      sx={{
                        fontWeight: 700,
                        fontSize: '0.6rem',
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                        color: isFailed ? 'error.main' : 'warning.main',
                      }}
                    >
                      {t('dialogs.prune.messagesLabel')}
                    </Typography>
                  </Box>
                )}
                <ColorizedOutput text={stderr} isFailed={isFailed} />
              </Box>
            )}
          </Box>
        ) : (
          <Box
            sx={{
              py: 4,
              textAlign: 'center',
              color: 'text.disabled',
              border: '1px solid',
              borderColor,
              borderRadius: 1.5,
            }}
          >
            <Typography variant="body2">{t('dialogs.prune.noArchivesWouldBeDeleted')}</Typography>
          </Box>
        )}

        {/* ── Contextual note below output ── */}
        {!isFailed && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: 'block', mt: 1.5, px: 0.25, lineHeight: 1.5 }}
          >
            {isDryRun ? t('dialogs.prune.dryRunNote') : t('dialogs.prune.pruneNote')}
          </Typography>
        )}
      </DialogContent>

      {/* ── Actions ── */}
      <DialogActions sx={{ px: 3, pb: 2.5, gap: 1 }}>
        {isDryRun && !isFailed ? (
          <>
            <Button variant="outlined" onClick={onClose}>
              {t('dialogs.prune.close')}
            </Button>
            <Button
              variant="contained"
              color="error"
              disabled={isLoading}
              startIcon={
                isLoading ? <CircularProgress size={15} color="inherit" /> : <Scissors size={15} />
              }
              onClick={() => onRunPrune(currentForm)}
              sx={{
                whiteSpace: 'nowrap',
                boxShadow: `0 2px 8px ${alpha(theme.palette.error.main, 0.35)}`,
              }}
            >
              {isLoading ? t('status.running') : t('dialogs.prune.runPruneNow')}
            </Button>
          </>
        ) : (
          <Button variant="contained" color={isFailed ? 'error' : 'primary'} onClick={onCloseAll}>
            {isFailed ? t('dialogs.prune.close') : t('dialogs.prune.done')}
          </Button>
        )}
      </DialogActions>
    </ResponsiveDialog>
  )
}

// ─── Config Dialog ────────────────────────────────────────────────────────────

export default function PruneRepositoryDialog({
  open,
  repository,
  onClose,
  onDryRun,
  onConfirmPrune,
  isLoading,
  results,
  initialForm,
}: PruneRepositoryDialogProps) {
  const { t, i18n } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const resolvedInitialForm = React.useMemo(
    () => ({ ...defaultPruneForm, ...initialForm }),
    [initialForm]
  )
  const [pruneForm, setPruneForm] = useState<PruneForm>(resolvedInitialForm)
  const [resultsOpen, setResultsOpen] = useState(false)
  const [activeOp, setActiveOp] = useState<'dry_run' | 'prune' | null>(null)

  React.useEffect(() => {
    if (open) setPruneForm(resolvedInitialForm)
  }, [open, resolvedInitialForm])

  // Clear active op when loading finishes
  React.useEffect(() => {
    if (!isLoading) setActiveOp(null)
  }, [isLoading])

  // Open the results dialog whenever new results arrive
  React.useEffect(() => {
    if (results) {
      setResultsOpen(true)
    }
  }, [results])

  const handleResultsClose = () => {
    setResultsOpen(false)
  }

  const handleResultsCloseAll = () => {
    setResultsOpen(false)
    onClose()
  }

  const handleRunPruneFromResults = (form: PruneForm) => {
    setResultsOpen(false)
    onConfirmPrune(form)
  }

  const retentionFields = [
    {
      key: 'keep_hourly' as const,
      icon: <Clock size={14} />,
      label: t('dialogs.prune.keepHourly'),
      unit: t('dialogs.prune.retentionUnits.hourly'),
    },
    {
      key: 'keep_daily' as const,
      icon: <Sun size={14} />,
      label: t('dialogs.prune.keepDaily'),
      unit: t('dialogs.prune.retentionUnits.daily'),
    },
    {
      key: 'keep_weekly' as const,
      icon: <CalendarDays size={14} />,
      label: t('dialogs.prune.keepWeekly'),
      unit: t('dialogs.prune.retentionUnits.weekly'),
    },
    {
      key: 'keep_monthly' as const,
      icon: <CalendarRange size={14} />,
      label: t('dialogs.prune.keepMonthly'),
      unit: t('dialogs.prune.retentionUnits.monthly'),
    },
    {
      key: 'keep_quarterly' as const,
      icon: <CalendarRange size={14} />,
      label: t('dialogs.prune.keepQuarterly'),
      unit: t('dialogs.prune.retentionUnits.quarterly'),
    },
    {
      key: 'keep_yearly' as const,
      icon: <Calendar size={14} />,
      label: t('dialogs.prune.keepYearly'),
      unit: t('dialogs.prune.retentionUnits.yearly'),
    },
  ]

  const borderColor = isDark ? alpha('#fff', 0.08) : alpha('#000', 0.09)
  const retentionSummary = formatRetentionList(
    retentionFields
      .filter((field) => pruneForm[field.key] > 0)
      .map((field) => `${pruneForm[field.key]} ${field.unit}`),
    i18n.resolvedLanguage || i18n.language
  )

  return (
    <>
      <ResponsiveDialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
        {/* ── Title ── */}
        <DialogTitle sx={{ pb: 1.5 }}>
          <Stack direction="row" spacing={1.5} alignItems="flex-start">
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 36,
                height: 36,
                borderRadius: 1.5,
                bgcolor: alpha(theme.palette.warning.main, isDark ? 0.18 : 0.1),
                color: theme.palette.warning.main,
                flexShrink: 0,
              }}
            >
              <Scissors size={18} />
            </Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="h6" fontWeight={600} lineHeight={1.3}>
                {t('dialogs.pruneRepository.title')}
              </Typography>
              {repository?.name && (
                <Typography
                  variant="body2"
                  color="text.secondary"
                  noWrap
                  sx={{ fontFamily: 'ui-monospace, monospace', fontSize: '0.72rem' }}
                >
                  {repository.name}
                </Typography>
              )}
            </Box>
            <Tooltip
              title={
                <Box>
                  <Typography variant="body2" fontWeight={600} gutterBottom>
                    {t('dialogs.prune.whatDoesPruningDo')}
                  </Typography>
                  <Typography variant="body2" gutterBottom>
                    {t('dialogs.prune.explanation')}
                  </Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {t('dialogs.prune.dryRunTip')}
                  </Typography>
                </Box>
              }
              arrow
              placement="top"
            >
              <Box
                sx={{
                  ml: 'auto',
                  display: 'flex',
                  color: 'text.disabled',
                  cursor: 'help',
                  flexShrink: 0,
                  mt: '3px',
                }}
              >
                <Info size={15} />
              </Box>
            </Tooltip>
          </Stack>
        </DialogTitle>

        <DialogContent sx={{ pt: 0 }}>
          {/* ── Retention policy ── */}
          <Typography
            variant="caption"
            sx={{
              display: 'block',
              fontWeight: 700,
              fontSize: '0.6rem',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'text.disabled',
              mb: 1,
            }}
          >
            {t('dialogs.prune.retentionPolicy')}
          </Typography>

          <Box
            sx={{
              border: '1px solid',
              borderColor,
              borderRadius: 1.5,
              overflow: 'hidden',
              mb: 0.75,
            }}
          >
            {retentionFields.map((field, i) => (
              <Box
                key={field.key}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1.5,
                  px: 1.75,
                  py: 0.9,
                  borderBottom: i < retentionFields.length - 1 ? '1px solid' : 0,
                  borderColor,
                  bgcolor: isDark ? alpha('#fff', 0.015) : alpha('#000', 0.012),
                  '&:hover': {
                    bgcolor: isDark ? alpha('#fff', 0.03) : alpha('#000', 0.025),
                  },
                  transition: 'background-color 150ms',
                }}
              >
                <Box sx={{ color: 'text.disabled', display: 'flex', flexShrink: 0 }}>
                  {field.icon}
                </Box>
                <Typography variant="body2" sx={{ flex: 1, fontSize: '0.8rem' }}>
                  {field.label}
                </Typography>
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    border: '1px solid',
                    borderColor,
                    borderRadius: 1,
                    px: 1,
                    py: 0.35,
                    bgcolor: 'background.paper',
                    width: 72,
                  }}
                >
                  <InputBase
                    type="number"
                    value={pruneForm[field.key]}
                    onChange={(e) =>
                      setPruneForm({ ...pruneForm, [field.key]: parseInt(e.target.value) || 0 })
                    }
                    inputProps={{ min: 0, style: { textAlign: 'center', padding: 0 } }}
                    sx={{
                      fontSize: '0.85rem',
                      fontWeight: 600,
                      fontVariantNumeric: 'tabular-nums',
                      flex: 1,
                    }}
                  />
                </Box>
              </Box>
            ))}
          </Box>

          <Typography
            variant="caption"
            color="text.disabled"
            sx={{ display: 'block', mb: 2, px: 0.25 }}
          >
            {retentionSummary
              ? t('dialogs.prune.exampleExplanation', { retention: retentionSummary })
              : t('dialogs.prune.noRetentionExample')}
          </Typography>

          {/* ── Warning strip ── */}
          <Box
            sx={{
              display: 'flex',
              gap: 1,
              alignItems: 'flex-start',
              p: 1.5,
              borderRadius: 1.5,
              border: '1px solid',
              borderColor: alpha(theme.palette.warning.main, 0.25),
              bgcolor: alpha(theme.palette.warning.main, isDark ? 0.08 : 0.05),
            }}
          >
            <Box
              sx={{ color: theme.palette.warning.main, display: 'flex', flexShrink: 0, mt: '1px' }}
            >
              <TriangleAlert size={14} />
            </Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography
                variant="body2"
                fontWeight={600}
                sx={{ fontSize: '0.8rem', color: isDark ? 'warning.light' : 'warning.dark' }}
              >
                {t('dialogs.prune.warningTitle')}
              </Typography>
              <Typography variant="body2" sx={{ fontSize: '0.78rem', color: 'text.secondary' }}>
                {t('dialogs.prune.warningCompact')}
              </Typography>
            </Box>
          </Box>
        </DialogContent>

        {/* ── Actions ── */}
        <DialogActions sx={{ px: 3, pb: 2.5, gap: 1 }}>
          <Button
            onClick={() => {
              setActiveOp('dry_run')
              onDryRun(pruneForm)
            }}
            variant="outlined"
            disabled={isLoading}
            startIcon={
              activeOp === 'dry_run' ? (
                <CircularProgress size={15} color="inherit" />
              ) : (
                <FlaskConical size={15} />
              )
            }
            sx={{ whiteSpace: 'nowrap' }}
          >
            {activeOp === 'dry_run' ? t('status.running') : t('dialogs.prune.dryRunButton')}
          </Button>
          <Button
            onClick={() => {
              setActiveOp('prune')
              onConfirmPrune(pruneForm)
            }}
            variant="contained"
            color="error"
            disabled={isLoading}
            startIcon={
              activeOp === 'prune' ? (
                <CircularProgress size={15} color="inherit" />
              ) : (
                <Scissors size={15} />
              )
            }
            sx={{
              whiteSpace: 'nowrap',
              boxShadow: `0 2px 8px ${alpha(theme.palette.error.main, 0.35)}`,
            }}
          >
            {activeOp === 'prune' ? t('status.running') : t('dialogs.pruneRepository.confirm')}
          </Button>
        </DialogActions>
      </ResponsiveDialog>

      {/* ── Results Dialog (separate overlay) ── */}
      {results && (
        <PruneResultsDialog
          open={resultsOpen}
          results={results}
          repository={repository}
          currentForm={pruneForm}
          isLoading={isLoading}
          onClose={handleResultsClose}
          onRunPrune={handleRunPruneFromResults}
          onCloseAll={handleResultsCloseAll}
        />
      )}
    </>
  )
}
