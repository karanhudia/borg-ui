import { Box, TextField, Divider, Typography, Checkbox, FormControlLabel } from '@mui/material'
import CodeEditor from './CodeEditor'

interface AdvancedRepositoryOptionsProps {
  mode: 'full' | 'observe'
  remotePath: string
  preBackupScript: string
  postBackupScript: string
  hookTimeout: number
  continueOnHookFailure: boolean
  customFlags: string
  onRemotePathChange: (value: string) => void
  onPreBackupScriptChange: (value: string) => void
  onPostBackupScriptChange: (value: string) => void
  onHookTimeoutChange: (value: number) => void
  onContinueOnHookFailureChange: (value: boolean) => void
  onCustomFlagsChange: (value: string) => void
}

export default function AdvancedRepositoryOptions({
  mode,
  remotePath,
  preBackupScript,
  postBackupScript,
  hookTimeout,
  continueOnHookFailure,
  customFlags,
  onRemotePathChange,
  onPreBackupScriptChange,
  onPostBackupScriptChange,
  onHookTimeoutChange,
  onContinueOnHookFailureChange,
  onCustomFlagsChange,
}: AdvancedRepositoryOptionsProps) {
  return (
    <>
      <Divider sx={{ mt: 2 }} />
      <Typography variant="subtitle2" fontWeight={600} sx={{ mt: 2 }}>
        Advanced Options
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
        Configure remote borg path, custom flags, and backup hooks for advanced use cases
      </Typography>

      {/* Remote Path */}
      <TextField
        label="Remote Borg Path (Optional)"
        value={remotePath}
        onChange={(e) => onRemotePathChange(e.target.value)}
        placeholder="/usr/local/bin/borg"
        fullWidth
        helperText="Path to borg binary on remote server (leave empty for default)"
      />

      {/* Custom Flags - Only show for full repositories */}
      {mode === 'full' && (
        <TextField
          label="Custom Flags (Optional)"
          value={customFlags}
          onChange={(e) => onCustomFlagsChange(e.target.value)}
          placeholder="--stats --list --filter AME"
          fullWidth
          helperText="Custom command-line flags for borg create (e.g., --stats, --progress, --list)"
        />
      )}

      {/* Backup Hooks - Only show for full repositories */}
      {mode === 'full' && (
        <>
          <Typography variant="subtitle2" fontWeight={600} sx={{ mt: 2, mb: 1 }}>
            Backup Hooks (Optional)
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
            Run custom scripts before and after backups (e.g., wake up NAS, send notifications)
          </Typography>

          <CodeEditor
            label="Pre-Backup Script"
            value={preBackupScript}
            onChange={onPreBackupScriptChange}
            placeholder="#!/bin/bash&#10;echo 'Pre-backup hook started'&#10;wakeonlan AA:BB:CC:DD:EE:FF&#10;sleep 60"
            helperText="Shell script to run before backup starts"
            height="150px"
          />

          <CodeEditor
            label="Post-Backup Script"
            value={postBackupScript}
            onChange={onPostBackupScriptChange}
            placeholder="#!/bin/bash&#10;echo 'Post-backup hook completed'&#10;ssh nas@192.168.1.100 'sudo poweroff'"
            helperText="Shell script to run after successful backup"
            height="150px"
          />

          <Box sx={{ display: 'flex', gap: 2, alignItems: 'flex-start' }}>
            <TextField
              label="Hook Timeout (seconds)"
              type="number"
              value={hookTimeout}
              onChange={(e) => onHookTimeoutChange(parseInt(e.target.value) || 300)}
              fullWidth
              helperText="Maximum time to wait for hooks"
            />

            <FormControlLabel
              control={
                <Checkbox
                  checked={continueOnHookFailure}
                  onChange={(e) => onContinueOnHookFailureChange(e.target.checked)}
                />
              }
              label="Continue if pre-hook fails"
              sx={{ mt: 1 }}
            />
          </Box>
        </>
      )}
    </>
  )
}
