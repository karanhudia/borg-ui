import { useEffect, useMemo, useState } from 'react'
import type { TFunction } from 'i18next'
import {
  Box,
  Button,
  Checkbox,
  DialogActions,
  DialogContent,
  DialogTitle,
  Link,
  Stack,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { Eraser, Save, AlertTriangle, CheckCircle2 } from 'lucide-react'

import ResponsiveDialog from '../../components/ResponsiveDialog'
import type { LegacySourceRepositoryReview } from './legacySourceSettings'

interface LegacySourceSettingsReviewDialogProps {
  open: boolean
  reviews: LegacySourceRepositoryReview[]
  saving: boolean
  onCancel: () => void
  onSaveWithoutClearing: () => void
  onSaveAndClear: (repositoryIds: number[]) => void
  t: TFunction
}

function PathListBlock({
  title,
  count,
  paths,
  tone,
}: {
  title: string
  count: number
  paths: string[]
  tone: 'warning' | 'info'
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  if (paths.length === 0) return null
  const color = tone === 'warning' ? theme.palette.warning.main : theme.palette.info.main
  return (
    <Box
      sx={{
        borderRadius: 1,
        border: '1px solid',
        borderColor: alpha(color, isDark ? 0.25 : 0.2),
        bgcolor: alpha(color, isDark ? 0.06 : 0.04),
        px: 1.25,
        py: 1,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.5 }}>
        <Typography
          variant="caption"
          sx={{
            fontWeight: 700,
            fontSize: '0.68rem',
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color,
          }}
        >
          {title}
        </Typography>
        <Typography
          variant="caption"
          sx={{
            fontSize: '0.65rem',
            color: 'text.disabled',
            fontWeight: 600,
          }}
        >
          ({count})
        </Typography>
      </Box>
      <Stack spacing={0.25}>
        {paths.map((path) => (
          <Typography
            key={path}
            variant="caption"
            sx={{
              fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
              fontSize: '0.72rem',
              color: 'text.primary',
              overflowWrap: 'anywhere',
              lineHeight: 1.5,
            }}
          >
            {path}
          </Typography>
        ))}
      </Stack>
    </Box>
  )
}

export function LegacySourceSettingsReviewDialog({
  open,
  reviews,
  saving,
  onCancel,
  onSaveWithoutClearing,
  onSaveAndClear,
  t,
}: LegacySourceSettingsReviewDialogProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const [selectedRepositoryIds, setSelectedRepositoryIds] = useState<Set<number>>(new Set())

  useEffect(() => {
    if (!open) return
    setSelectedRepositoryIds(
      new Set(reviews.filter((review) => review.defaultClear).map((review) => review.repository.id))
    )
  }, [open, reviews])

  const toggleRepository = (repositoryId: number) => {
    setSelectedRepositoryIds((current) => {
      const next = new Set(current)
      if (next.has(repositoryId)) {
        next.delete(repositoryId)
      } else {
        next.add(repositoryId)
      }
      return next
    })
  }

  const selectedIds = useMemo(() => Array.from(selectedRepositoryIds), [selectedRepositoryIds])
  const canClearSelected = selectedIds.length > 0
  const allSelected = reviews.length > 0 && selectedIds.length === reviews.length

  const handleToggleAll = () => {
    if (allSelected) {
      setSelectedRepositoryIds(new Set())
    } else {
      setSelectedRepositoryIds(new Set(reviews.map((r) => r.repository.id)))
    }
  }

  return (
    <ResponsiveDialog
      open={open}
      onClose={saving ? undefined : onCancel}
      maxWidth="md"
      fullWidth
      aria-labelledby="legacy-source-settings-review-title"
      footer={
        <DialogActions sx={{ px: 3, py: 2, gap: 1 }}>
          <Button onClick={onCancel} disabled={saving} sx={{ textTransform: 'none' }}>
            {t('common.buttons.cancel')}
          </Button>
          <Button
            variant="outlined"
            onClick={onSaveWithoutClearing}
            disabled={saving}
            startIcon={<Save size={15} />}
            sx={{ textTransform: 'none' }}
          >
            {t('backupPlans.wizard.repositories.legacyReview.saveWithoutClearing')}
          </Button>
          <Button
            variant="contained"
            color="warning"
            onClick={() => onSaveAndClear(selectedIds)}
            disabled={saving || !canClearSelected}
            startIcon={<Eraser size={15} />}
            sx={{ textTransform: 'none' }}
          >
            {t('backupPlans.wizard.repositories.legacyReview.saveAndClearSelected')}
          </Button>
        </DialogActions>
      }
    >
      <DialogTitle
        id="legacy-source-settings-review-title"
        sx={{ pb: 0.5, display: 'flex', flexDirection: 'column', gap: 0.25 }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box
            sx={{
              color: theme.palette.warning.main,
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <AlertTriangle size={18} />
          </Box>
          <Typography component="span" variant="h6" sx={{ fontWeight: 700 }}>
            {t('backupPlans.wizard.repositories.legacyReview.title')}
          </Typography>
        </Box>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ fontSize: '0.8rem', lineHeight: 1.5, pl: 3.5 }}
        >
          {t('backupPlans.wizard.repositories.legacyReview.description')}
        </Typography>
      </DialogTitle>
      <DialogContent
        dividers
        sx={{ bgcolor: isDark ? alpha('#fff', 0.015) : alpha('#000', 0.012) }}
      >
        {reviews.length > 1 && (
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 1,
              mb: 1.5,
              px: 0.25,
            }}
          >
            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.72rem' }}>
              {selectedIds.length} / {reviews.length}
            </Typography>
            <Link
              component="button"
              type="button"
              onClick={handleToggleAll}
              disabled={saving}
              underline="hover"
              sx={{
                fontSize: '0.72rem',
                fontWeight: 600,
                cursor: 'pointer',
                color: 'primary.main',
              }}
            >
              {allSelected
                ? t('backupPlans.wizard.repositories.legacyReview.deselectAll')
                : t('backupPlans.wizard.repositories.legacyReview.selectAll')}
            </Link>
          </Box>
        )}

        <Stack spacing={1.5}>
          {reviews.map((review) => {
            const repositoryLabel = review.repository.name || review.repository.path
            const checked = selectedRepositoryIds.has(review.repository.id)
            const hasExactMatch = review.comparison === 'matches'
            const legacyOnlyCount = review.legacyOnlySourceDirectories.length

            return (
              <Box
                key={review.repository.id}
                sx={{
                  border: '1px solid',
                  borderColor: checked
                    ? alpha(theme.palette.warning.main, isDark ? 0.45 : 0.4)
                    : isDark
                      ? alpha('#fff', 0.1)
                      : alpha('#000', 0.1),
                  borderRadius: 1.5,
                  bgcolor: 'background.paper',
                  overflow: 'hidden',
                  transition: 'border-color 0.15s',
                }}
              >
                {/* Header row */}
                <Box
                  component="label"
                  htmlFor={`legacy-review-${review.repository.id}`}
                  sx={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 1,
                    p: 1.5,
                    cursor: saving ? 'default' : 'pointer',
                  }}
                >
                  <Checkbox
                    id={`legacy-review-${review.repository.id}`}
                    checked={checked}
                    onChange={() => toggleRepository(review.repository.id)}
                    disabled={saving}
                    size="small"
                    color="warning"
                    sx={{ p: 0.25, mt: 0.125 }}
                  />
                  <Box sx={{ minWidth: 0, flex: 1 }}>
                    <Typography
                      variant="body2"
                      sx={{ fontWeight: 700, fontSize: '0.875rem', lineHeight: 1.3 }}
                    >
                      {repositoryLabel}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{
                        fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
                        fontSize: '0.7rem',
                        color: 'text.disabled',
                        overflowWrap: 'anywhere',
                      }}
                    >
                      {review.repository.path}
                    </Typography>
                  </Box>
                  {legacyOnlyCount > 0 && (
                    <Box
                      sx={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 0.4,
                        px: 0.75,
                        py: 0.25,
                        borderRadius: 0.75,
                        bgcolor: alpha(theme.palette.warning.main, isDark ? 0.15 : 0.1),
                        border: '1px solid',
                        borderColor: alpha(theme.palette.warning.main, isDark ? 0.35 : 0.25),
                        flexShrink: 0,
                        height: 22,
                      }}
                    >
                      <AlertTriangle size={11} color={theme.palette.warning.main} />
                      <Typography
                        sx={{
                          fontSize: '0.68rem',
                          fontWeight: 700,
                          color: theme.palette.warning.main,
                          lineHeight: 1,
                        }}
                      >
                        {t('backupPlans.wizard.repositories.legacyReview.extraPathsCount', {
                          count: legacyOnlyCount,
                        })}
                      </Typography>
                    </Box>
                  )}
                </Box>

                {/* Diff blocks */}
                {hasExactMatch ? (
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.75,
                      px: 1.5,
                      pb: 1.5,
                      color: theme.palette.success.main,
                    }}
                  >
                    <CheckCircle2 size={14} />
                    <Typography variant="caption" sx={{ fontSize: '0.75rem' }}>
                      {t('backupPlans.wizard.repositories.legacyReview.matchesHelper')}
                    </Typography>
                  </Box>
                ) : (
                  <Stack spacing={1} sx={{ px: 1.5, pb: 1.5 }}>
                    <PathListBlock
                      title={t('backupPlans.wizard.repositories.legacyReview.willBeCleared')}
                      count={review.legacyOnlySourceDirectories.length}
                      paths={review.legacyOnlySourceDirectories}
                      tone="warning"
                    />
                    <PathListBlock
                      title={t('backupPlans.wizard.repositories.legacyReview.planWillBackUp')}
                      count={review.planOnlySourceDirectories.length}
                      paths={review.planOnlySourceDirectories}
                      tone="info"
                    />
                  </Stack>
                )}
              </Box>
            )
          })}
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}
