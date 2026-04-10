import React from 'react'
import {
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Box,
  Typography,
  Stack,
  useTheme,
  alpha,
} from '@mui/material'
import type { SxProps, Theme } from '@mui/material'
import { Database } from 'lucide-react'
import { Repository } from '../types'
import RepoMenuItem from './RepoMenuItem'
import BorgVersionChip from './BorgVersionChip'

interface RepoSelectProps {
  repositories: Repository[]
  value: number | string
  onChange: (value: number | string) => void
  loading?: boolean
  /** 'id' returns repo.id as item value; 'path' returns repo.path */
  valueKey?: 'id' | 'path'
  label?: string
  loadingLabel?: string
  placeholderLabel?: string
  fallbackDisplayValue?: string
  maintenanceLabel?: string
  size?: 'small' | 'medium'
  disabled?: boolean
  hidePath?: boolean
  /** Extra MenuItems rendered before the repo list (e.g. an "All" option) */
  prefixItems?: React.ReactNode
  fullWidth?: boolean
  sx?: SxProps<Theme>
}

export default function RepoSelect({
  repositories,
  value,
  onChange,
  loading = false,
  valueKey = 'path',
  label = 'Repository',
  loadingLabel = 'Loading…',
  placeholderLabel = 'Select a repository',
  fallbackDisplayValue,
  maintenanceLabel,
  size = 'medium',
  disabled = false,
  hidePath = false,
  prefixItems,
  fullWidth = true,
  sx,
}: RepoSelectProps) {
  const theme = useTheme()

  // Find selected repo for rich renderValue
  const selectedRepo =
    value && value !== ''
      ? repositories.find((r) => (valueKey === 'id' ? r.id === value : r.path === value))
      : null

  const selectSx: SxProps<Theme> =
    size === 'medium'
      ? {
          minHeight: { xs: 52, sm: 58 },
          '& .MuiSelect-select': {
            display: 'flex',
            alignItems: 'center',
          },
          ...sx,
        }
      : {
          '& .MuiSelect-select': {
            display: 'flex',
            alignItems: 'center',
          },
          ...sx,
        }

  return (
    <FormControl
      fullWidth={fullWidth}
      size={size}
      sx={{ minWidth: { xs: '100%', sm: 300 }, ...sx }}
    >
      {label && <InputLabel>{label}</InputLabel>}
      <Select
        value={value}
        onChange={(e) => onChange(e.target.value as number | string)}
        label={label || undefined}
        disabled={disabled || loading}
        sx={selectSx}
        renderValue={(val) => {
          if (loading) {
            return (
              <Typography variant="body2" color="text.secondary">
                {loadingLabel}
              </Typography>
            )
          }
          if (!val || val === '' || !selectedRepo) {
            if (val && val !== '' && fallbackDisplayValue) {
              return (
                <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 600 }}>
                  {fallbackDisplayValue}
                </Typography>
              )
            }
            return (
              <Typography variant="body2" color="text.disabled">
                {placeholderLabel}
              </Typography>
            )
          }

          if (size === 'small') {
            // Compact: icon + name only
            return (
              <Stack direction="row" spacing={0.75} alignItems="center">
                <Database size={13} />
                <Typography variant="body2" fontWeight={500} noWrap>
                  {selectedRepo.name}
                </Typography>
                <BorgVersionChip borgVersion={selectedRepo.borg_version} compact />
              </Stack>
            )
          }

          // Medium: icon + name + monospace path
          return (
            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              sx={{ minWidth: 0, flex: 1, overflow: 'hidden' }}
            >
              <Database size={16} style={{ flexShrink: 0 }} />
              <Box sx={{ minWidth: 0, flex: 1 }}>
                <Stack direction="row" spacing={0.5} alignItems="center">
                  <Typography variant="body2" fontWeight={600} noWrap sx={{ lineHeight: 1.3 }}>
                    {selectedRepo.name}
                  </Typography>
                  <BorgVersionChip borgVersion={selectedRepo.borg_version} compact />
                </Stack>
                <Typography
                  sx={{
                    fontFamily:
                      '"JetBrains Mono","Fira Code",ui-monospace,SFMono-Regular,monospace',
                    fontSize: '0.62rem',
                    color: 'text.disabled',
                    lineHeight: 1.4,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {selectedRepo.path}
                </Typography>
              </Box>
            </Stack>
          )
        }}
      >
        {prefixItems}
        {!prefixItems && (
          <MenuItem value="" disabled>
            {loading ? loadingLabel : placeholderLabel}
          </MenuItem>
        )}
        {repositories.map((repo) => (
          <MenuItem
            key={repo.id}
            value={valueKey === 'id' ? repo.id : repo.path}
            disabled={repo.has_running_maintenance}
            sx={{
              minWidth: 0,
              overflow: 'hidden',
              '&.Mui-selected': {
                bgcolor: alpha(
                  theme.palette.primary.main,
                  theme.palette.mode === 'dark' ? 0.14 : 0.08
                ),
              },
            }}
          >
            <RepoMenuItem
              name={repo.name}
              path={repo.path}
              borgVersion={repo.borg_version}
              mode={repo.mode as 'full' | 'observe' | undefined}
              hasRunningMaintenance={repo.has_running_maintenance}
              maintenanceLabel={maintenanceLabel}
              hidePath={hidePath}
            />
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  )
}
