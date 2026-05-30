import { type KeyboardEventHandler, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { TextField, IconButton, InputAdornment } from '@mui/material'
import FolderOpen from '@mui/icons-material/FolderOpen'
import FileExplorerDialog from '../FileExplorerDialog'

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
  initialPath?: string
  onSelectPaths?: (paths: string[]) => void
  onKeyDown?: KeyboardEventHandler<HTMLDivElement>
  connectionType?: 'local' | 'ssh' | 'agent'
  agentId?: number
  agentName?: string
  agentDefaultPath?: string | null
  sshConfig?: {
    ssh_key_id: number
    host: string
    username: string
    port: number
  }
  showSshMountPoints?: boolean
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
  initialPath,
  onSelectPaths,
  onKeyDown,
  connectionType = 'local',
  agentId,
  agentName,
  agentDefaultPath,
  sshConfig,
  showSshMountPoints,
  fullWidth = true,
  size = 'small',
}: PathSelectorFieldProps) {
  const { t } = useTranslation()
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
        onKeyDown={onKeyDown}
        InputProps={{
          endAdornment: (
            <InputAdornment position="end">
              <IconButton
                onClick={() => setShowFileExplorer(true)}
                edge="end"
                size="small"
                title={t('pathSelectorField.browseFilesystem')}
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
            if (onSelectPaths) {
              onSelectPaths(paths)
            } else {
              onChange(multiSelect ? paths.join(',') : paths[0])
            }
          }
        }}
        title={
          selectMode === 'directories'
            ? t('pathSelectorField.selectDirectory')
            : selectMode === 'files'
              ? t('pathSelectorField.selectFile')
              : t('pathSelectorField.selectPath')
        }
        initialPath={initialPath || value || '/'}
        multiSelect={multiSelect}
        connectionType={connectionType}
        agentId={agentId}
        agentName={agentName}
        agentDefaultPath={agentDefaultPath}
        sshConfig={sshConfig}
        selectMode={selectMode}
        showSshMountPoints={showSshMountPoints}
      />
    </>
  )
}
