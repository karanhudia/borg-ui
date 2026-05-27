import { alpha } from '@mui/material'

/** Shared sx for Select controls placed inside ListToolbar or its extraFilters slot. */
export function listToolbarSelectSx(isDark: boolean, minWidth = 160) {
  return {
    flex: 1,
    minWidth,
    fontSize: '0.8rem',
    fontWeight: 600,
    borderRadius: 1.5,
    '& .MuiOutlinedInput-notchedOutline': {
      borderColor: isDark ? alpha('#fff', 0.1) : alpha('#000', 0.12),
    },
    '&:hover .MuiOutlinedInput-notchedOutline': {
      borderColor: isDark ? alpha('#fff', 0.2) : alpha('#000', 0.25),
    },
  }
}
