import { useState } from 'react'
import {
  Alert,
  Box,
  DialogContent,
  DialogTitle,
  IconButton,
  InputAdornment,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import ResponsiveDialog from '../shared/ResponsiveDialog'
import PlanGate from '../shared/PlanGate'
import { usePlan } from '../../hooks/usePlan'
import { archivesAPI } from '../../services/api'
import { parseBackendDate } from '../../utils/dateUtils'

interface ArchiveSearchFieldProps {
  repositoryId: number
  newestArchiveId: number | null
}

export default function ArchiveSearchField({
  repositoryId,
  newestArchiveId,
}: ArchiveSearchFieldProps) {
  const { t } = useTranslation()
  const { can } = usePlan()
  const [query, setQuery] = useState('')
  const [submitted, setSubmitted] = useState('')
  const disabled = !can('archive_history')

  const { data, isLoading } = useQuery({
    queryKey: ['archive-search', repositoryId, submitted],
    queryFn: () => archivesAPI.search(repositoryId, submitted).then((res) => res.data),
    enabled: submitted.length > 0,
  })

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (disabled || !query.trim()) return
    setSubmitted(query.trim())
  }

  return (
    <PlanGate feature="archive_history" disabled surface="archives" operation="search">
      <Box component="form" role="search" onSubmit={handleSubmit}>
        <TextField
          size="small"
          placeholder={t('archives.search.placeholder')}
          value={query}
          disabled={disabled}
          onChange={(e) => setQuery(e.target.value)}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <IconButton type="submit" size="small" edge="start" disabled={disabled}>
                    <SearchIcon fontSize="small" />
                  </IconButton>
                </InputAdornment>
              ),
            },
          }}
        />
      </Box>
      <ResponsiveDialog
        open={submitted.length > 0}
        onClose={() => setSubmitted('')}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>{t('archives.search.title')}</DialogTitle>
        <DialogContent>
          {!isLoading && data && data.results.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              {t('archives.search.empty')}
            </Typography>
          )}
          {data && data.results.length > 0 && (
            <>
              {data.truncated && (
                <Alert severity="info" sx={{ mb: 1.5 }}>
                  {t('archives.search.truncated', { count: data.results.length })}
                </Alert>
              )}
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('archives.search.columnPath')}</TableCell>
                    <TableCell>{t('archives.search.columnLastSeen')}</TableCell>
                    <TableCell>{t('archives.search.columnPresent')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {data.results.map((result) => (
                    <TableRow key={result.path}>
                      <TableCell>{result.path}</TableCell>
                      <TableCell>{parseBackendDate(result.last_seen).toLocaleString()}</TableCell>
                      <TableCell>
                        {result.last_seen_archive_id === newestArchiveId
                          ? t('archives.search.present')
                          : t('archives.search.absent')}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </>
          )}
        </DialogContent>
      </ResponsiveDialog>
    </PlanGate>
  )
}
