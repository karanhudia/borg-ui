import {
  Box,
  InputBase,
  MenuItem,
  Select,
  alpha,
  useTheme,
  type SelectChangeEvent,
} from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import type { ReactNode } from 'react'
import { listToolbarSelectSx } from './listToolbarStyles'

export interface ListToolbarOption {
  value: string
  label: string
}

interface ListToolbarProps {
  searchValue: string
  onSearchChange: (value: string) => void
  searchPlaceholder?: string
  sortValue?: string
  onSortChange?: (value: string) => void
  sortOptions?: ListToolbarOption[]
  sortMinWidth?: number
  groupValue?: string
  onGroupChange?: (value: string) => void
  groupOptions?: ListToolbarOption[]
  groupMinWidth?: number
  /** Additional filter controls rendered after the group select on the same row. */
  extraFilters?: ReactNode
}

export default function ListToolbar({
  searchValue,
  onSearchChange,
  searchPlaceholder,
  sortValue,
  onSortChange,
  sortOptions,
  sortMinWidth = 180,
  groupValue,
  onGroupChange,
  groupOptions,
  groupMinWidth = 140,
  extraFilters,
}: ListToolbarProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const borderColor = isDark ? alpha('#fff', 0.1) : alpha('#000', 0.12)
  const hoverBorderColor = isDark ? alpha('#fff', 0.2) : alpha('#000', 0.25)

  const selectSx = (minWidth: number) => listToolbarSelectSx(isDark, minWidth)

  const handleSortChange = (event: SelectChangeEvent<string>) => {
    onSortChange?.(event.target.value)
  }

  const handleGroupChange = (event: SelectChangeEvent<string>) => {
    onGroupChange?.(event.target.value)
  }

  return (
    <Box
      sx={{
        mb: 3,
        display: 'flex',
        flexWrap: 'wrap',
        gap: 1.5,
        alignItems: 'center',
      }}
    >
      <Box
        sx={{
          flex: '1 1 100%',
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          px: 1.5,
          height: 40,
          borderRadius: 1.5,
          border: '1px solid',
          borderColor,
          bgcolor: isDark ? alpha('#fff', 0.04) : alpha('#000', 0.02),
          '&:focus-within': { borderColor: hoverBorderColor },
        }}
      >
        <SearchIcon sx={{ fontSize: 16, color: 'text.disabled', flexShrink: 0 }} />
        <InputBase
          placeholder={searchPlaceholder}
          value={searchValue}
          onChange={(e) => onSearchChange(e.target.value)}
          sx={{ flex: 1, fontSize: '0.875rem', minWidth: 0 }}
          inputProps={{ 'aria-label': searchPlaceholder }}
        />
      </Box>

      {sortOptions && sortValue !== undefined && onSortChange ? (
        <Select
          size="small"
          value={sortValue}
          onChange={handleSortChange}
          sx={selectSx(sortMinWidth)}
        >
          {sortOptions.map((option) => (
            <MenuItem key={option.value} value={option.value}>
              {option.label}
            </MenuItem>
          ))}
        </Select>
      ) : null}

      {groupOptions && groupValue !== undefined && onGroupChange ? (
        <Select
          size="small"
          value={groupValue}
          onChange={handleGroupChange}
          sx={selectSx(groupMinWidth)}
        >
          {groupOptions.map((option) => (
            <MenuItem key={option.value} value={option.value}>
              {option.label}
            </MenuItem>
          ))}
        </Select>
      ) : null}

      {extraFilters}
    </Box>
  )
}
