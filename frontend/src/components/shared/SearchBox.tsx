import { Box, InputBase, alpha, useTheme } from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import type { SxProps, Theme } from '@mui/material'

interface SearchBoxProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
  sx?: SxProps<Theme>
}

/** The list pages' search bar: a bordered row with a quiet icon and a
 * plain input. One look for every search on the product. */
export default function SearchBox({ value, onChange, placeholder, disabled, sx }: SearchBoxProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  return (
    <Box
      sx={[
        {
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          px: 1.5,
          height: 40,
          borderRadius: 1.5,
          border: '1px solid',
          borderColor: isDark ? alpha('#fff', 0.1) : alpha('#000', 0.12),
          bgcolor: isDark ? alpha('#fff', 0.04) : alpha('#000', 0.02),
          '&:focus-within': { borderColor: isDark ? alpha('#fff', 0.2) : alpha('#000', 0.25) },
        },
        ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
      ]}
    >
      <SearchIcon sx={{ fontSize: 16, color: 'text.disabled', flexShrink: 0 }} />
      <InputBase
        placeholder={placeholder}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        sx={{ flex: 1, fontSize: '0.875rem', minWidth: 0 }}
        inputProps={{ 'aria-label': placeholder }}
      />
    </Box>
  )
}
