import { Box, InputAdornment, MenuItem, Select, TextField, Typography } from '@mui/material'
import { Search } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { FILTER_SELECT_SX } from '../activity/filterSelectSx'
import {
  ATTENTION_FILTERS,
  HUB_SORTS,
  type AttentionFilter,
  type HubSort,
  type HubToolbarState,
} from './hubRows'

interface HubToolbarProps {
  state: HubToolbarState
  onChange: (next: HubToolbarState) => void
  // How many rows the table is showing out of how many the toolbar
  // matched, so a person knows the list is windowed.
  shown: number
  total: number
}

const ATTENTION_LABEL: Record<AttentionFilter, string> = {
  all: 'operations.background.hub.filterAll',
  attention: 'operations.background.hub.filterAttention',
  stale: 'operations.background.hub.filterStale',
  never: 'operations.background.hub.filterNever',
  history: 'operations.background.hub.filterHistory',
  running: 'operations.background.hub.filterRunning',
}

const SORT_LABEL: Record<HubSort, string> = {
  name: 'operations.background.hub.sortName',
  rows: 'operations.background.hub.sortRows',
  synced: 'operations.background.hub.sortSynced',
}

// Name filter, attention filter and sort for the repository table. State is
// owned by the board so the summary strip can set the attention filter too.
export default function HubToolbar({ state, onChange, shown, total }: HubToolbarProps) {
  const { t } = useTranslation()
  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
      <TextField
        size="small"
        value={state.query}
        onChange={(event) => onChange({ ...state, query: event.target.value })}
        placeholder={t('operations.background.hub.filterName')}
        slotProps={{
          htmlInput: { 'aria-label': t('operations.background.hub.filterName') },
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <Search size={16} />
              </InputAdornment>
            ),
          },
        }}
        sx={{
          minWidth: 200,
          flex: { xs: '1 1 100%', sm: '0 1 260px' },
          '& .MuiOutlinedInput-root': { ...FILTER_SELECT_SX, fontWeight: 400 },
        }}
      />
      <Select
        size="small"
        value={state.attention}
        onChange={(event) =>
          onChange({ ...state, attention: event.target.value as AttentionFilter })
        }
        inputProps={{ 'aria-label': t('operations.background.hub.filterShow') }}
        sx={FILTER_SELECT_SX}
      >
        {ATTENTION_FILTERS.map((value) => (
          <MenuItem key={value} value={value}>
            {t(ATTENTION_LABEL[value])}
          </MenuItem>
        ))}
      </Select>
      <Select
        size="small"
        value={state.sort}
        onChange={(event) => onChange({ ...state, sort: event.target.value as HubSort })}
        inputProps={{ 'aria-label': t('operations.background.hub.sortBy') }}
        sx={FILTER_SELECT_SX}
      >
        {HUB_SORTS.map((value) => (
          <MenuItem key={value} value={value}>
            {t(SORT_LABEL[value])}
          </MenuItem>
        ))}
      </Select>
      {shown < total && (
        <Typography
          variant="caption"
          sx={{ color: 'text.secondary', ml: { sm: 'auto' }, fontVariantNumeric: 'tabular-nums' }}
        >
          {t('operations.background.hub.shownOf', { shown, total })}
        </Typography>
      )}
    </Box>
  )
}
