import { Box, TextField } from '@mui/material'
import { useTranslation } from 'react-i18next'

import { MAX_FILES, MAX_MEMORY, MIN_FILES, MIN_MEMORY } from './constants'

interface ArchiveBrowsingLimitsSectionProps {
  browseMaxItems: number
  browseMaxMemoryMb: number
  setBrowseMaxItems: (value: number) => void
  setBrowseMaxMemoryMb: (value: number) => void
}

const ArchiveBrowsingLimitsSection: React.FC<ArchiveBrowsingLimitsSectionProps> = ({
  browseMaxItems,
  browseMaxMemoryMb,
  setBrowseMaxItems,
  setBrowseMaxMemoryMb,
}) => {
  const { t } = useTranslation()

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' },
        gap: 2,
      }}
    >
      <TextField
        label={t('systemSettings.maxFilesToLoadLabel')}
        type="number"
        fullWidth
        value={browseMaxItems}
        onChange={(e) => setBrowseMaxItems(Number(e.target.value))}
        inputProps={{ min: MIN_FILES, max: MAX_FILES, step: 100_000 }}
        error={browseMaxItems < MIN_FILES || browseMaxItems > MAX_FILES}
        helperText={
          browseMaxItems < MIN_FILES || browseMaxItems > MAX_FILES
            ? t('systemSettings.maxFilesRangeError', {
                min: MIN_FILES.toLocaleString(),
                max: MAX_FILES.toLocaleString(),
              })
            : t('systemSettings.maxFilesHelperText', {
                current: (browseMaxItems / 1_000_000).toFixed(1),
              })
        }
      />

      <TextField
        label={t('systemSettings.maxMemoryLabel')}
        type="number"
        fullWidth
        value={browseMaxMemoryMb}
        onChange={(e) => setBrowseMaxMemoryMb(Number(e.target.value))}
        inputProps={{ min: MIN_MEMORY, max: MAX_MEMORY, step: 128 }}
        error={browseMaxMemoryMb < MIN_MEMORY || browseMaxMemoryMb > MAX_MEMORY}
        helperText={
          browseMaxMemoryMb < MIN_MEMORY || browseMaxMemoryMb > MAX_MEMORY
            ? t('systemSettings.maxMemoryRangeError', {
                min: MIN_MEMORY,
                max: MAX_MEMORY,
              })
            : t('systemSettings.maxMemoryHelperText', {
                current: (browseMaxMemoryMb / 1024).toFixed(2),
              })
        }
      />
    </Box>
  )
}

export default ArchiveBrowsingLimitsSection
