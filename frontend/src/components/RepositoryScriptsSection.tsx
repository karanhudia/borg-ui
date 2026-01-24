import { Box, Button, Typography, Chip, Tooltip } from '@mui/material'
import { FileCode } from 'lucide-react'
import RepositoryScriptsTab from './RepositoryScriptsTab'

interface RepositoryScriptsSectionProps {
  repositoryId?: number | null
  // Inline scripts
  preBackupScript: string
  postBackupScript: string
  onPreBackupScriptChange: (value: string) => void
  onPostBackupScriptChange: (value: string) => void
  // Dialogs
  onOpenPreScriptDialog: () => void
  onOpenPostScriptDialog: () => void
  // Library script state
  hasPreLibraryScripts?: boolean
  hasPostLibraryScripts?: boolean
  onPreLibraryScriptsChange?: (hasScripts: boolean) => void
  onPostLibraryScriptsChange?: (hasScripts: boolean) => void
}

export default function RepositoryScriptsSection({
  repositoryId,
  preBackupScript,
  postBackupScript,
  onPreBackupScriptChange,
  onPostBackupScriptChange,
  onOpenPreScriptDialog,
  onOpenPostScriptDialog,
  hasPreLibraryScripts = false,
  hasPostLibraryScripts = false,
  onPreLibraryScriptsChange,
  onPostLibraryScriptsChange,
}: RepositoryScriptsSectionProps) {
  return (
    <>
      {/* Pre-Backup Scripts */}
      <Box sx={{ mb: 1.5 }}>
        <Box
          sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.75 }}
        >
          <Typography variant="body2" fontWeight={600}>
            Pre-Backup Scripts
          </Typography>
          <Tooltip
            title={
              !repositoryId
                ? 'Create the repository first to add library scripts'
                : 'Add script from library'
            }
            arrow
          >
            <span>
              <Button
                variant="outlined"
                size="small"
                startIcon={<FileCode size={14} />}
                onClick={() => {
                  if (repositoryId) {
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    const openFn = (window as any)[`openScriptDialog_${repositoryId}_pre-backup`]
                    if (openFn) openFn()
                  }
                }}
                disabled={!repositoryId}
                sx={{ py: 0.25, px: 1, minHeight: 'auto', fontSize: '0.8rem' }}
              >
                Add
              </Button>
            </span>
          </Tooltip>
        </Box>

        {/* Inline Pre-Backup Script - hidden when library scripts exist */}
        {!hasPreLibraryScripts && (
          <Box sx={{ mb: repositoryId ? 1 : 0 }}>
            <Button
              variant="outlined"
              startIcon={<FileCode size={18} />}
              onClick={onOpenPreScriptDialog}
              fullWidth
              sx={{ justifyContent: 'flex-start', textTransform: 'none' }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                <Typography>Inline Script</Typography>
                {preBackupScript && (
                  <Chip label="Configured" size="small" color="success" sx={{ ml: 'auto' }} />
                )}
              </Box>
            </Button>
          </Box>
        )}

        {/* Library Pre-Backup Scripts */}
        {repositoryId && (
          <RepositoryScriptsTab
            repositoryId={repositoryId}
            hookType="pre-backup"
            onScriptsChange={onPreLibraryScriptsChange}
            hasInlineScript={!!preBackupScript}
            onClearInlineScript={() => onPreBackupScriptChange('')}
          />
        )}
      </Box>

      {/* Post-Backup Scripts */}
      <Box>
        <Box
          sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.75 }}
        >
          <Typography variant="body2" fontWeight={600}>
            Post-Backup Scripts
          </Typography>
          <Tooltip
            title={
              !repositoryId
                ? 'Create the repository first to add library scripts'
                : 'Add script from library'
            }
            arrow
          >
            <span>
              <Button
                variant="outlined"
                size="small"
                startIcon={<FileCode size={14} />}
                onClick={() => {
                  if (repositoryId) {
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    const openFn = (window as any)[`openScriptDialog_${repositoryId}_post-backup`]
                    if (openFn) openFn()
                  }
                }}
                disabled={!repositoryId}
                sx={{ py: 0.25, px: 1, minHeight: 'auto', fontSize: '0.8rem' }}
              >
                Add
              </Button>
            </span>
          </Tooltip>
        </Box>

        {/* Inline Post-Backup Script - hidden when library scripts exist */}
        {!hasPostLibraryScripts && (
          <Box sx={{ mb: repositoryId ? 1 : 0 }}>
            <Button
              variant="outlined"
              startIcon={<FileCode size={18} />}
              onClick={onOpenPostScriptDialog}
              fullWidth
              sx={{ justifyContent: 'flex-start', textTransform: 'none' }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                <Typography>Inline Script</Typography>
                {postBackupScript && (
                  <Chip label="Configured" size="small" color="success" sx={{ ml: 'auto' }} />
                )}
              </Box>
            </Button>
          </Box>
        )}

        {/* Library Post-Backup Scripts */}
        {repositoryId && (
          <RepositoryScriptsTab
            repositoryId={repositoryId}
            hookType="post-backup"
            onScriptsChange={onPostLibraryScriptsChange}
            hasInlineScript={!!postBackupScript}
            onClearInlineScript={() => onPostBackupScriptChange('')}
          />
        )}
      </Box>
    </>
  )
}
