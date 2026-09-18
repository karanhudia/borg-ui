import { useTranslation } from 'react-i18next'
import {
  Alert,
  Box,
  Button,
  ButtonBase,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { formatBytes, formatDateTimeFull } from '../../utils/dateUtils'
import { formatRetention } from './formatRetention'
import type {
  PruneComparison,
  PruneComparisonRow,
  StoredPruneRetention,
} from '../../types/archives'

export interface EditingRow {
  retention: StoredPruneRetention
  kept_count: number
  deleted_count: number
  freed_at_least: number
}

interface Props {
  comparison: PruneComparison | null
  editing: EditingRow | null
  selectedKey: string | null
  pending: boolean
  refreshDisabled: boolean
  onSelect: (row: PruneComparisonRow) => void
  onRefresh: () => void
}

export function PruneComparedPolicies({
  comparison,
  editing,
  selectedKey,
  pending,
  refreshDisabled,
  onSelect,
  onRefresh,
}: Props) {
  const { t } = useTranslation()
  const rows = comparison?.candidates ?? []
  const label = (row: PruneComparisonRow) =>
    row.key === 'current'
      ? row.retention
        ? t('prunePreview.compare.current')
        : t('prunePreview.compare.currentNoPolicy')
      : t(`prunePreview.compare.presets.${row.key}`, { defaultValue: row.label })
  const partial = rows.some((r) => r.partial_measure)

  return (
    <Paper variant="outlined" sx={{ p: 2, mt: 3 }}>
      <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
        <Box>
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
            {t('prunePreview.compare.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {pending
              ? t('prunePreview.compare.comparing')
              : comparison?.computed_at
                ? t('prunePreview.compare.computedOn', {
                    date: formatDateTimeFull(comparison.computed_at),
                  })
                : t('prunePreview.compare.notYet')}
          </Typography>
        </Box>
        <Button
          size="small"
          variant="outlined"
          onClick={onRefresh}
          disabled={refreshDisabled || pending}
        >
          {t('prunePreview.compare.compareNow')}
        </Button>
      </Stack>
      {comparison?.stale && rows.length > 0 && !pending && (
        <Alert severity="info" sx={{ mb: 1 }}>
          {t('prunePreview.compare.stale')}
        </Alert>
      )}
      {(rows.length > 0 || editing) && (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('prunePreview.compare.colPolicy')}</TableCell>
                <TableCell>{t('prunePreview.compare.colRetention')}</TableCell>
                <TableCell align="right">{t('prunePreview.compare.colKept')}</TableCell>
                <TableCell align="right">{t('prunePreview.compare.colDeleted')}</TableCell>
                <TableCell align="right">{t('prunePreview.compare.colFree')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.key} selected={row.key === selectedKey} hover>
                  <TableCell>
                    <ButtonBase
                      onClick={() => onSelect(row)}
                      sx={{ fontWeight: 600, textAlign: 'left' }}
                    >
                      {label(row)}
                    </ButtonBase>
                  </TableCell>
                  <TableCell sx={{ fontFamily: 'monospace' }}>
                    {formatRetention(row.retention)}
                  </TableCell>
                  <TableCell align="right">{row.kept_count}</TableCell>
                  <TableCell align="right">{row.deleted_count}</TableCell>
                  <TableCell align="right">{formatBytes(row.freed_at_least)}</TableCell>
                </TableRow>
              ))}
              {editing && (
                <TableRow selected>
                  <TableCell>
                    <Chip size="small" label={t('prunePreview.compare.editing')} />
                  </TableCell>
                  <TableCell sx={{ fontFamily: 'monospace' }}>
                    {formatRetention(editing.retention)}
                  </TableCell>
                  <TableCell align="right">{editing.kept_count}</TableCell>
                  <TableCell align="right">{editing.deleted_count}</TableCell>
                  <TableCell align="right">{formatBytes(editing.freed_at_least)}</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </Box>
      )}
      {partial && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          {t('prunePreview.compare.partial')}
        </Typography>
      )}
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
        {t('prunePreview.compare.intro')}
      </Typography>
    </Paper>
  )
}
