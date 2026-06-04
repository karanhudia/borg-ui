import { Box, TextField } from '@mui/material'
import { useTranslation } from 'react-i18next'

import { formatTimeout, MAX_TIMEOUT, MIN_TIMEOUT } from './constants'
import { SourceLabel } from './SourceLabel'

interface OperationTimeoutsSectionProps {
  mountTimeout: number
  infoTimeout: number
  listTimeout: number
  initTimeout: number
  backupTimeout: number
  sourceSizeTimeout: number
  timeoutSources?: Record<string, string | null>
  setMountTimeout: (value: number) => void
  setInfoTimeout: (value: number) => void
  setListTimeout: (value: number) => void
  setInitTimeout: (value: number) => void
  setBackupTimeout: (value: number) => void
  setSourceSizeTimeout: (value: number) => void
}

const OperationTimeoutsSection: React.FC<OperationTimeoutsSectionProps> = ({
  mountTimeout,
  infoTimeout,
  listTimeout,
  initTimeout,
  backupTimeout,
  sourceSizeTimeout,
  timeoutSources,
  setMountTimeout,
  setInfoTimeout,
  setListTimeout,
  setInitTimeout,
  setBackupTimeout,
  setSourceSizeTimeout,
}) => {
  const { t } = useTranslation()

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', md: '1fr 1fr', xl: '1fr 1fr 1fr' },
        gap: 2,
      }}
    >
      <TextField
        label={t('systemSettings.mountTimeoutLabel')}
        type="number"
        fullWidth
        value={mountTimeout}
        onChange={(e) => setMountTimeout(Number(e.target.value))}
        inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 10 }}
        error={mountTimeout < MIN_TIMEOUT || mountTimeout > MAX_TIMEOUT}
        helperText={
          <>
            {t('systemSettings.mountTimeoutHelper')} {formatTimeout(mountTimeout)}
            <SourceLabel source={timeoutSources?.mount_timeout} />
          </>
        }
      />

      <TextField
        label={t('systemSettings.infoTimeoutLabel')}
        type="number"
        fullWidth
        value={infoTimeout}
        onChange={(e) => setInfoTimeout(Number(e.target.value))}
        inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 60 }}
        error={infoTimeout < MIN_TIMEOUT || infoTimeout > MAX_TIMEOUT}
        helperText={
          <>
            {t('systemSettings.infoTimeoutHelper')} {formatTimeout(infoTimeout)}
            <SourceLabel source={timeoutSources?.info_timeout} />
          </>
        }
      />

      <TextField
        label={t('systemSettings.listTimeoutLabel')}
        type="number"
        fullWidth
        value={listTimeout}
        onChange={(e) => setListTimeout(Number(e.target.value))}
        inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 60 }}
        error={listTimeout < MIN_TIMEOUT || listTimeout > MAX_TIMEOUT}
        helperText={
          <>
            {t('systemSettings.listTimeoutHelper')} {formatTimeout(listTimeout)}
            <SourceLabel source={timeoutSources?.list_timeout} />
          </>
        }
      />

      <TextField
        label={t('systemSettings.initTimeoutLabel')}
        type="number"
        fullWidth
        value={initTimeout}
        onChange={(e) => setInitTimeout(Number(e.target.value))}
        inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 60 }}
        error={initTimeout < MIN_TIMEOUT || initTimeout > MAX_TIMEOUT}
        helperText={
          <>
            {t('systemSettings.initTimeoutHelper')} {formatTimeout(initTimeout)}
            <SourceLabel source={timeoutSources?.init_timeout} />
          </>
        }
      />

      <TextField
        label={t('systemSettings.backupTimeoutLabel')}
        type="number"
        fullWidth
        value={backupTimeout}
        onChange={(e) => setBackupTimeout(Number(e.target.value))}
        inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 300 }}
        error={backupTimeout < MIN_TIMEOUT || backupTimeout > MAX_TIMEOUT}
        helperText={
          <>
            {t('systemSettings.backupTimeoutHelper')} {formatTimeout(backupTimeout)}
            <SourceLabel source={timeoutSources?.backup_timeout} />
          </>
        }
      />

      <TextField
        label={t('systemSettings.sourceSizeTimeoutLabel')}
        type="number"
        fullWidth
        value={sourceSizeTimeout}
        onChange={(e) => setSourceSizeTimeout(Number(e.target.value))}
        inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 300 }}
        error={sourceSizeTimeout < MIN_TIMEOUT || sourceSizeTimeout > MAX_TIMEOUT}
        helperText={
          <>
            {t('systemSettings.sourceSizeTimeoutHelper')} {formatTimeout(sourceSizeTimeout)}
            <SourceLabel source={timeoutSources?.source_size_timeout} />
          </>
        }
      />
    </Box>
  )
}

export default OperationTimeoutsSection
