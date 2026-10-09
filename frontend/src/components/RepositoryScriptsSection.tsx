import { Alert, Box, Button, Typography, Chip, Tooltip } from '@mui/material'
import { useTranslation } from 'react-i18next'
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
  // An agent repository runs only scripts its agent publishes: no inline
  // script is offered, and one stored from before is shown as never run.
  agentRepository?: boolean
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
  agentRepository = false,
}: RepositoryScriptsSectionProps) {
  const { t } = useTranslation()

  const addTooltip = !repositoryId
    ? t(
        agentRepository
          ? 'repositoryScriptsSection.createFirstAgent'
          : 'repositoryScriptsSection.createFirst'
      )
    : t(
        agentRepository
          ? 'repositoryScriptsSection.addAgentScript'
          : 'repositoryScriptsSection.addFromLibrary'
      )

  const inlineNotRun = (onRemove: () => void) => (
    <Alert
      severity="warning"
      sx={{ mb: repositoryId ? 1 : 0 }}
      action={
        <Button color="inherit" size="small" onClick={onRemove}>
          {t('repositoryScriptsSection.removeInline')}
        </Button>
      }
    >
      {t('repositoryScriptsSection.inlineNotRun')}
    </Alert>
  )

  return (
    <>
      {/* Pre-Backup Scripts */}
      <Box sx={{ mb: 1.5 }}>
        <Box
          sx={{
            display: 'flex',
            flexDirection: { xs: 'column', sm: 'row' },
            justifyContent: 'space-between',
            alignItems: { xs: 'stretch', sm: 'center' },
            gap: 1,
            mb: 0.75,
          }}
        >
          <Typography
            variant="body2"
            sx={{
              fontWeight: 600,
            }}
          >
            {t('repositoryScriptsSection.preBackup')}
          </Typography>
          <Tooltip title={addTooltip} arrow>
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
                sx={{
                  py: 0.25,
                  px: 1,
                  minHeight: 'auto',
                  fontSize: '0.8rem',
                  width: { xs: '100%', sm: 'auto' },
                }}
              >
                {t('repositoryScriptsSection.add')}
              </Button>
            </span>
          </Tooltip>
        </Box>

        {agentRepository && preBackupScript && inlineNotRun(() => onPreBackupScriptChange(''))}

        {/* Inline Pre-Backup Script - hidden when library scripts exist */}
        {!agentRepository && !hasPreLibraryScripts && (
          <Box sx={{ mb: repositoryId ? 1 : 0 }}>
            <Button
              variant="outlined"
              startIcon={<FileCode size={18} />}
              onClick={onOpenPreScriptDialog}
              fullWidth
              sx={{ justifyContent: 'flex-start', textTransform: 'none' }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                <Typography>{t('repositoryScriptsSection.inlineScript')}</Typography>
                {preBackupScript && (
                  <Chip
                    label={t('repositoryScriptsSection.configured')}
                    size="small"
                    color="success"
                    sx={{ ml: 'auto' }}
                  />
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
            agentRepository={agentRepository}
          />
        )}
      </Box>

      {/* Post-Backup Scripts */}
      <Box>
        <Box
          sx={{
            display: 'flex',
            flexDirection: { xs: 'column', sm: 'row' },
            justifyContent: 'space-between',
            alignItems: { xs: 'stretch', sm: 'center' },
            gap: 1,
            mb: 0.75,
          }}
        >
          <Typography
            variant="body2"
            sx={{
              fontWeight: 600,
            }}
          >
            {t('repositoryScriptsSection.postBackup')}
          </Typography>
          <Tooltip title={addTooltip} arrow>
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
                sx={{
                  py: 0.25,
                  px: 1,
                  minHeight: 'auto',
                  fontSize: '0.8rem',
                  width: { xs: '100%', sm: 'auto' },
                }}
              >
                {t('repositoryScriptsSection.add')}
              </Button>
            </span>
          </Tooltip>
        </Box>

        {agentRepository && postBackupScript && inlineNotRun(() => onPostBackupScriptChange(''))}

        {/* Inline Post-Backup Script - hidden when library scripts exist */}
        {!agentRepository && !hasPostLibraryScripts && (
          <Box sx={{ mb: repositoryId ? 1 : 0 }}>
            <Button
              variant="outlined"
              startIcon={<FileCode size={18} />}
              onClick={onOpenPostScriptDialog}
              fullWidth
              sx={{ justifyContent: 'flex-start', textTransform: 'none' }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                <Typography>{t('repositoryScriptsSection.inlineScript')}</Typography>
                {postBackupScript && (
                  <Chip
                    label={t('repositoryScriptsSection.configured')}
                    size="small"
                    color="success"
                    sx={{ ml: 'auto' }}
                  />
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
            agentRepository={agentRepository}
          />
        )}
      </Box>
    </>
  )
}
