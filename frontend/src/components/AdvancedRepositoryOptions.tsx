import { useState } from 'react'
import {
  Box,
  TextField,
  Divider,
  Typography,
  Checkbox,
  FormControlLabel,
  Button,
  Chip,
} from '@mui/material'
import { FileCode } from 'lucide-react'
import ScriptEditorDialog from './ScriptEditorDialog'
import RepositoryScriptsTab from './RepositoryScriptsTab'

interface AdvancedRepositoryOptionsProps {
  repositoryId?: number | null
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
  repositoryId,
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
  const [preScriptDialogOpen, setPreScriptDialogOpen] = useState(false)
  const [postScriptDialogOpen, setPostScriptDialogOpen] = useState(false)

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

      {/* Backup Hooks - Only show for full repositories without ID (create/import) */}
      {/* When editing (repositoryId exists), use Script Library instead */}
      {mode === 'full' && !repositoryId && (
        <>
          <Typography variant="subtitle2" fontWeight={600} sx={{ mt: 2, mb: 1 }}>
            Backup Hooks (Optional) - Legacy
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
            Simple inline scripts. After creation, use Script Library for advanced features (run on failure, etc.)
          </Typography>

          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
            <Box>
              <Button
                variant="outlined"
                startIcon={<FileCode size={18} />}
                onClick={() => setPreScriptDialogOpen(true)}
                fullWidth
                sx={{ justifyContent: 'flex-start', textTransform: 'none' }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                  <Typography>Pre-Backup Script</Typography>
                  {preBackupScript && (
                    <Chip label="Configured" size="small" color="success" sx={{ ml: 'auto' }} />
                  )}
                </Box>
              </Button>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ ml: 1, mt: 0.5, display: 'block' }}
              >
                Shell script to run before backup starts
              </Typography>
            </Box>

            <Box>
              <Button
                variant="outlined"
                startIcon={<FileCode size={18} />}
                onClick={() => setPostScriptDialogOpen(true)}
                fullWidth
                sx={{ justifyContent: 'flex-start', textTransform: 'none' }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                  <Typography>Post-Backup Script</Typography>
                  {postBackupScript && (
                    <Chip label="Configured" size="small" color="success" sx={{ ml: 'auto' }} />
                  )}
                </Box>
              </Button>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ ml: 1, mt: 0.5, display: 'block' }}
              >
                Shell script to run after successful backup
              </Typography>
            </Box>
          </Box>

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

      {/* Script Editor Dialogs */}
      <ScriptEditorDialog
        open={preScriptDialogOpen}
        onClose={() => setPreScriptDialogOpen(false)}
        title="Pre-Backup Script"
        value={preBackupScript}
        onChange={onPreBackupScriptChange}
        placeholder="#!/bin/bash&#10;echo 'Pre-backup hook started'&#10;wakeonlan AA:BB:CC:DD:EE:FF&#10;sleep 60"
      />

      <ScriptEditorDialog
        open={postScriptDialogOpen}
        onClose={() => setPostScriptDialogOpen(false)}
        title="Post-Backup Script"
        value={postBackupScript}
        onChange={onPostBackupScriptChange}
        placeholder="#!/bin/bash&#10;echo 'Post-backup hook completed'&#10;ssh nas@192.168.1.100 'sudo poweroff'"
      />

      {/* Script Library - Only show for full repositories with ID */}
      {mode === 'full' && repositoryId && (
        <>
          <Divider sx={{ mt: 3, mb: 2 }} />
          <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 0.5 }}>
            Backup Scripts
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
            Assign reusable scripts with advanced conditions (run on failure, run always, chaining, etc.)
          </Typography>
          <RepositoryScriptsTab repositoryId={repositoryId} />
        </>
      )}
    </>
  )
}
