import { useTranslation } from 'react-i18next'
import ArchivePathSelector, { type ArchivePathSelectionData } from '../ArchivePathSelector'
import type { Repository } from '../../services/borgApi/client'
import type { Archive } from '../../types'

export type RestoreFilesStepData = ArchivePathSelectionData

interface WizardStepRestoreFilesProps {
  repository: Repository
  archive: Pick<Archive, 'id' | 'name'>
  data: RestoreFilesStepData
  onChange: (data: Partial<RestoreFilesStepData>) => void
  title?: string
  subtitle?: string
  helpText?: string
}

export default function WizardStepRestoreFiles({
  repository,
  archive,
  data,
  onChange,
  title,
  subtitle,
  helpText,
}: WizardStepRestoreFilesProps) {
  const { t } = useTranslation()
  return (
    <ArchivePathSelector
      repository={repository}
      archive={archive}
      data={data}
      onChange={onChange}
      title={title || t('wizard.restoreFiles.title')}
      subtitle={subtitle || t('wizard.restoreFiles.subtitle')}
      helpText={helpText || t('wizard.restoreFiles.helpText')}
    />
  )
}
