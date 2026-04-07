import React from 'react'
import { FormControl, InputLabel, MenuItem, Select } from '@mui/material'
import type { SxProps, Theme } from '@mui/material'
import { Repository } from '../types'
import RepoMenuItem from './RepoMenuItem'

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
  maintenanceLabel,
  size = 'medium',
  disabled = false,
  hidePath = false,
  prefixItems,
  fullWidth = true,
  sx,
}: RepoSelectProps) {
  const selectSx = size === 'medium' ? { height: { xs: 48, sm: 56 }, ...sx } : sx

  return (
    <FormControl
      fullWidth={fullWidth}
      size={size}
      sx={{ minWidth: { xs: '100%', sm: 300 }, ...sx }}
    >
      <InputLabel>{label}</InputLabel>
      <Select
        value={value}
        onChange={(e) => onChange(e.target.value as number | string)}
        label={label}
        disabled={disabled || loading}
        sx={selectSx}
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
