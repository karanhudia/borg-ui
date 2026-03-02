import React from 'react'
import { useTranslation } from 'react-i18next'
import { TextField, Stack, Alert } from '@mui/material'
import MultiRepositorySelector from '../../MultiRepositorySelector'
import { Repository } from '../../../types'

interface WizardStepBasicInfoData {
  name: string
  description: string
  repositoryIds: number[]
}

interface WizardStepBasicInfoProps {
  data: WizardStepBasicInfoData
  repositories: Repository[]
  onChange: (updates: Partial<WizardStepBasicInfoData>) => void
}

const WizardStepBasicInfo: React.FC<WizardStepBasicInfoProps> = ({
  data,
  repositories,
  onChange,
}) => {
  const { t } = useTranslation()

  return (
    <Stack spacing={2}>
      <TextField
        label={t('wizard.scheduleWizard.basicInfo.jobNameLabel')}
        value={data.name}
        onChange={(e) => onChange({ name: e.target.value })}
        required
        fullWidth
        placeholder={t('wizard.scheduleWizard.basicInfo.jobNamePlaceholder')}
        size="medium"
        InputProps={{
          sx: { fontSize: '1.1rem' },
        }}
        InputLabelProps={{
          sx: { fontSize: '1.1rem' },
        }}
      />

      <TextField
        label={t('wizard.scheduleWizard.basicInfo.descriptionLabel')}
        value={data.description}
        onChange={(e) => onChange({ description: e.target.value })}
        multiline
        rows={2}
        placeholder={t('wizard.scheduleWizard.basicInfo.descriptionPlaceholder')}
        fullWidth
        size="medium"
        InputProps={{
          sx: { fontSize: '1.1rem' },
        }}
        InputLabelProps={{
          sx: { fontSize: '1.1rem' },
        }}
      />

      <MultiRepositorySelector
        repositories={repositories}
        selectedIds={data.repositoryIds}
        onChange={(ids) => onChange({ repositoryIds: ids })}
        label={t('wizard.scheduleWizard.basicInfo.repositoriesLabel')}
        placeholder={t('wizard.scheduleWizard.basicInfo.repositoriesPlaceholder')}
        helperText={t('wizard.scheduleWizard.basicInfo.repositoriesHelper')}
        required
        size="medium"
        allowReorder={true}
        filterMode="observe"
      />

      {data.repositoryIds.length === 0 && (
        <Alert severity="warning" sx={{ py: 0.5 }}>
          {t('wizard.scheduleWizard.basicInfo.selectAtLeastOne')}
        </Alert>
      )}
    </Stack>
  )
}

export default WizardStepBasicInfo
