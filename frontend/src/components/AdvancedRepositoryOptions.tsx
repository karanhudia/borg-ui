import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { TextField, Divider, Typography } from '@mui/material'
import ScriptEditorDialog from './ScriptEditorDialog'
import RepositoryScriptsSection from './RepositoryScriptsSection'

interface AdvancedRepositoryOptionsProps {
  repositoryId?: number | null
  mode: 'full' | 'observe'
  remotePath: string
  preBackupScript: string
  postBackupScript: string
  preHookTimeout: number
  postHookTimeout: number
  continueOnHookFailure: boolean
  customFlags: string
  onRemotePathChange: (value: string) => void
  onPreBackupScriptChange: (value: string) => void
  onPostBackupScriptChange: (value: string) => void
  onPreHookTimeoutChange: (value: number) => void
  onPostHookTimeoutChange: (value: number) => void
  onContinueOnHookFailureChange: (value: boolean) => void
  onCustomFlagsChange: (value: string) => void
}

export default function AdvancedRepositoryOptions({
  repositoryId,
  mode,
  remotePath,
  preBackupScript,
  postBackupScript,
  preHookTimeout,
  postHookTimeout,
  continueOnHookFailure,
  customFlags,
  onRemotePathChange,
  onPreBackupScriptChange,
  onPostBackupScriptChange,
  onPreHookTimeoutChange,
  onPostHookTimeoutChange,
  onContinueOnHookFailureChange,
  onCustomFlagsChange,
}: AdvancedRepositoryOptionsProps) {
  const { t } = useTranslation()
  const [preScriptDialogOpen, setPreScriptDialogOpen] = useState(false)
  const [postScriptDialogOpen, setPostScriptDialogOpen] = useState(false)
  const [hasPreLibraryScripts, setHasPreLibraryScripts] = useState(false)
  const [hasPostLibraryScripts, setHasPostLibraryScripts] = useState(false)

  return (
    <>
      <Divider sx={{ mt: 2 }} />
      <Typography variant="subtitle2" fontWeight={600} sx={{ mt: 2 }}>
        {t('advancedRepositoryOptions.title')}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
        {t('advancedRepositoryOptions.subtitle')}
      </Typography>

      {/* Remote Path */}
      <TextField
        label={t('advancedRepositoryOptions.remoteBorgPath')}
        value={remotePath}
        onChange={(e) => onRemotePathChange(e.target.value)}
        placeholder="/usr/local/bin/borg"
        fullWidth
        helperText={t('advancedRepositoryOptions.remoteBorgPathHint')}
      />

      {/* Custom Flags - Only show for full repositories */}
      {mode === 'full' && (
        <TextField
          label={t('advancedRepositoryOptions.customFlags')}
          value={customFlags}
          onChange={(e) => onCustomFlagsChange(e.target.value)}
          placeholder="--stats --list --filter AME"
          fullWidth
          helperText={t('advancedRepositoryOptions.customFlagsHint')}
        />
      )}

      {/* Scripts Section - Grouped by timing (pre-backup / post-backup) */}
      {mode === 'full' && (
        <>
          <Divider sx={{ mt: 3, mb: 1.5 }} />
          <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 0.5 }}>
            {t('advancedRepositoryOptions.scripts')}
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
            {t('advancedRepositoryOptions.scriptsHint')}
          </Typography>

          <RepositoryScriptsSection
            repositoryId={repositoryId}
            preBackupScript={preBackupScript}
            postBackupScript={postBackupScript}
            onPreBackupScriptChange={onPreBackupScriptChange}
            onPostBackupScriptChange={onPostBackupScriptChange}
            onOpenPreScriptDialog={() => setPreScriptDialogOpen(true)}
            onOpenPostScriptDialog={() => setPostScriptDialogOpen(true)}
            hasPreLibraryScripts={hasPreLibraryScripts}
            hasPostLibraryScripts={hasPostLibraryScripts}
            onPreLibraryScriptsChange={setHasPreLibraryScripts}
            onPostLibraryScriptsChange={setHasPostLibraryScripts}
          />
        </>
      )}

      {/* Script Editor Dialogs */}
      <ScriptEditorDialog
        open={preScriptDialogOpen}
        onClose={() => setPreScriptDialogOpen(false)}
        title={t('advancedRepositoryOptions.preBackupScript')}
        value={preBackupScript}
        onChange={onPreBackupScriptChange}
        placeholder="#!/bin/bash&#10;echo 'Pre-backup hook started'&#10;wakeonlan AA:BB:CC:DD:EE:FF&#10;sleep 60"
        timeout={preHookTimeout}
        onTimeoutChange={onPreHookTimeoutChange}
        continueOnFailure={continueOnHookFailure}
        onContinueOnFailureChange={onContinueOnHookFailureChange}
        showContinueOnFailure={true}
        repositoryId={repositoryId}
      />

      <ScriptEditorDialog
        open={postScriptDialogOpen}
        onClose={() => setPostScriptDialogOpen(false)}
        title={t('advancedRepositoryOptions.postBackupScript')}
        value={postBackupScript}
        onChange={onPostBackupScriptChange}
        placeholder="#!/bin/bash&#10;echo 'Post-backup hook completed'&#10;ssh nas@192.168.1.100 'sudo poweroff'"
        timeout={postHookTimeout}
        onTimeoutChange={onPostHookTimeoutChange}
        showContinueOnFailure={false}
        repositoryId={repositoryId}
      />
    </>
  )
}
