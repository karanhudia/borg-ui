import React from 'react'
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
  return (
    <Stack spacing={2}>
      <TextField
        label="Job Name"
        value={data.name}
        onChange={(e) => onChange({ name: e.target.value })}
        required
        fullWidth
        placeholder="Daily backup"
        size="medium"
        InputProps={{
          sx: { fontSize: '1.1rem' },
        }}
        InputLabelProps={{
          sx: { fontSize: '1.1rem' },
        }}
      />

      <TextField
        label="Description"
        value={data.description}
        onChange={(e) => onChange({ description: e.target.value })}
        multiline
        rows={2}
        placeholder="Optional description"
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
        label="Repositories"
        placeholder="Select repositories..."
        helperText="Use arrows to change backup order."
        required
        size="medium"
        allowReorder={true}
        filterMode="observe"
      />

      {data.repositoryIds.length === 0 && (
        <Alert severity="warning" sx={{ py: 0.5 }}>
          Select at least one repository to continue.
        </Alert>
      )}
    </Stack>
  )
}

export default WizardStepBasicInfo
