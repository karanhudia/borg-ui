import { useState } from 'react'
import { TextField, IconButton, InputAdornment } from '@mui/material'
import { FolderOpen } from '@mui/icons-material'
import FileExplorerDialog from './FileExplorerDialog'

interface PathSelectorFieldProps {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  helperText?: string
  disabled?: boolean
  required?: boolean
  error?: boolean
  multiSelect?: boolean
  selectMode?: 'directories' | 'files' | 'both'
  connectionType?: 'local' | 'ssh'
  sshConfig?: {
    ssh_key_id: number
    host: string
    username: string
    port: number
  }
  fullWidth?: boolean
  size?: 'small' | 'medium'
}

export default function PathSelectorField({
  label,
  value,
  onChange,
  placeholder = '/path/to/directory',
  helperText,
  disabled = false,
  required = false,
  error = false,
  multiSelect = false,
  selectMode = 'directories',
  connectionType = 'local',
  sshConfig,
  fullWidth = true,
  size = 'small',
}: PathSelectorFieldProps) {
  const [showFileExplorer, setShowFileExplorer] = useState(false)

  return (
    <>
      <TextField
        fullWidth={fullWidth}
        size={size}
        label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        helperText={helperText}
        disabled={disabled}
        required={required}
        error={error}
        InputProps={{
          endAdornment: (
            <InputAdornment position="end">
              <IconButton
                onClick={() => setShowFileExplorer(true)}
                edge="end"
                size="small"
                title="Browse filesystem"
                disabled={disabled}
              >
                <FolderOpen fontSize="small" />
              </IconButton>
            </InputAdornment>
          ),
        }}
      />

      <FileExplorerDialog
        open={showFileExplorer}
        onClose={() => setShowFileExplorer(false)}
        onSelect={(paths) => {
          if (paths.length > 0) {
            onChange(multiSelect ? paths.join(',') : paths[0])
          }
        }}
        title={`Select ${selectMode === 'directories' ? 'Directory' : selectMode === 'files' ? 'File' : 'Path'}`}
        initialPath="/"
        multiSelect={multiSelect}
        connectionType={connectionType}
        sshConfig={sshConfig}
        selectMode={selectMode}
      />
    </>
  )
}
