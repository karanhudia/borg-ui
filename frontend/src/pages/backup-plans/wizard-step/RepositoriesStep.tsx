import {
  Alert,
  Box,
  Button,
  CircularProgress,
  IconButton,
  InputAdornment,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import { Plus } from 'lucide-react'

import MultiRepositorySelector from '../../../components/MultiRepositorySelector'
import {
  getDefaultRepositoryEncryption,
  RepositoryEncryptionFields,
} from '../../../components/wizard'
import type { BackupPlanWizardStepProps } from './types'

type RepositoriesStepProps = Pick<
  BackupPlanWizardStepProps,
  | 'wizardState'
  | 'basicRepositoryState'
  | 'basicRepositoryOpen'
  | 'fullRepositories'
  | 'loadingRepositories'
  | 'canUseMultiRepository'
  | 'canUseBorg2'
  | 'repositoryCreatePending'
  | 'updateBasicRepositoryState'
  | 'handleRepositoryIdsChange'
  | 'createBasicRepository'
  | 'setBasicRepositoryOpen'
  | 'setRepositoryWizardOpen'
  | 'setShowBasicRepositoryPathExplorer'
  | 't'
>

export function RepositoriesStep({
  wizardState,
  basicRepositoryState,
  basicRepositoryOpen,
  fullRepositories,
  loadingRepositories,
  canUseMultiRepository,
  canUseBorg2,
  repositoryCreatePending,
  updateBasicRepositoryState,
  handleRepositoryIdsChange,
  createBasicRepository,
  setBasicRepositoryOpen,
  setRepositoryWizardOpen,
  setShowBasicRepositoryPathExplorer,
  t,
}: RepositoriesStepProps) {
  const showBasicRepositoryForm = basicRepositoryOpen || fullRepositories.length === 0
  const canCreateBasicRepository = Boolean(
    basicRepositoryState.name.trim() &&
    basicRepositoryState.path.trim() &&
    (basicRepositoryState.encryption === 'none' || basicRepositoryState.passphrase.trim()) &&
    (basicRepositoryState.borgVersion !== 2 || canUseBorg2) &&
    !repositoryCreatePending
  )

  return (
    <Stack spacing={3}>
      {fullRepositories.length === 0 ? (
        <Alert severity="info">{t('backupPlans.wizard.repositories.noStorageTargets')}</Alert>
      ) : (
        <MultiRepositorySelector
          repositories={fullRepositories}
          selectedIds={wizardState.repositoryIds}
          onChange={handleRepositoryIdsChange}
          label={t('backupPlans.wizard.fields.repositories')}
          helperText={
            canUseMultiRepository
              ? t('backupPlans.wizard.repositories.helperPro')
              : t('backupPlans.wizard.repositories.helperCommunity')
          }
          placeholder={t('backupPlans.wizard.repositories.placeholder')}
          required
          allowReorder
          filterMode="observe"
          getOptionDisabled={(repository) =>
            !canUseMultiRepository &&
            wizardState.repositoryIds.length >= 1 &&
            !wizardState.repositoryIds.includes(repository.id)
          }
          disabled={loadingRepositories}
        />
      )}
      <Box
        sx={{
          border: 1,
          borderColor: 'divider',
          borderRadius: 2,
          bgcolor: 'background.default',
          p: 2,
        }}
      >
        <Stack spacing={2}>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={1.5}
            alignItems={{ xs: 'stretch', sm: 'center' }}
            justifyContent="space-between"
          >
            <Box>
              <Typography variant="subtitle2">
                {t('backupPlans.wizard.repositories.addStorageTarget')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t('backupPlans.wizard.repositories.basicDescription')}
              </Typography>
            </Box>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              {fullRepositories.length > 0 && (
                <Button
                  variant={showBasicRepositoryForm ? 'contained' : 'outlined'}
                  startIcon={<Plus size={16} />}
                  onClick={() => setBasicRepositoryOpen((prev) => !prev)}
                >
                  {t('backupPlans.wizard.repositories.basic')}
                </Button>
              )}
              <Button variant="outlined" onClick={() => setRepositoryWizardOpen(true)}>
                {t('backupPlans.wizard.repositories.advancedSetup')}
              </Button>
            </Stack>
          </Stack>

          {showBasicRepositoryForm && (
            <>
              <Alert severity="info">{t('backupPlans.wizard.repositories.advancedNotice')}</Alert>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                <TextField
                  label={t('backupPlans.wizard.fields.repositoryName')}
                  value={basicRepositoryState.name}
                  onChange={(event) => updateBasicRepositoryState({ name: event.target.value })}
                  required
                  fullWidth
                />
                <TextField
                  select
                  label={t('backupPlans.wizard.fields.borgVersion')}
                  value={basicRepositoryState.borgVersion}
                  onChange={(event) => {
                    const borgVersion = Number(event.target.value) === 2 ? 2 : 1
                    updateBasicRepositoryState({
                      borgVersion,
                      encryption: getDefaultRepositoryEncryption(borgVersion),
                    })
                  }}
                  sx={{ minWidth: { xs: '100%', md: 160 } }}
                >
                  <MenuItem value={1}>Borg 1</MenuItem>
                  <MenuItem value={2} disabled={!canUseBorg2}>
                    Borg 2{canUseBorg2 ? '' : ` (${t('backupPlans.status.pro')})`}
                  </MenuItem>
                </TextField>
              </Stack>
              <TextField
                label={t('backupPlans.wizard.fields.repositoryPath')}
                value={basicRepositoryState.path}
                onChange={(event) => updateBasicRepositoryState({ path: event.target.value })}
                placeholder="/backups/photos"
                helperText={t('backupPlans.wizard.repositories.pathHelper')}
                required
                fullWidth
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        onClick={() => setShowBasicRepositoryPathExplorer(true)}
                        edge="end"
                        size="small"
                        title={t('backupPlans.wizard.repositories.browsePath')}
                      >
                        <FolderOpenIcon fontSize="small" />
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
              />
              <RepositoryEncryptionFields
                mode="create"
                borgVersion={basicRepositoryState.borgVersion}
                data={{
                  encryption: basicRepositoryState.encryption,
                  passphrase: basicRepositoryState.passphrase,
                }}
                onChange={updateBasicRepositoryState}
              />
              <Button
                variant="contained"
                startIcon={
                  repositoryCreatePending ? (
                    <CircularProgress size={14} color="inherit" />
                  ) : (
                    <Plus size={16} />
                  )
                }
                onClick={createBasicRepository}
                disabled={!canCreateBasicRepository}
                sx={{ alignSelf: 'flex-start' }}
              >
                {t('backupPlans.wizard.repositories.createAndSelect')}
              </Button>
            </>
          )}
        </Stack>
      </Box>
    </Stack>
  )
}
