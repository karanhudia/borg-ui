import { Box, MenuItem, Select, useTheme, type SelectChangeEvent } from '@mui/material'
import SearchBox from './shared/SearchBox'
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
      <SearchBox
        value={searchValue}
        onChange={onSearchChange}
        placeholder={searchPlaceholder}
        sx={{ flex: '1 1 100%' }}
      />

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
