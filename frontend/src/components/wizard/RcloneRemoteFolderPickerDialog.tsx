import { useTranslation } from 'react-i18next'
import FileExplorerDialog from '../FileExplorerDialog'

interface RcloneRemoteFolderPickerDialogProps {
  open: boolean
  remoteId: number | null
  initialPath?: string
  onClose: () => void
  onSelect: (path: string) => void
}

export default function RcloneRemoteFolderPickerDialog({
  open,
  remoteId,
  initialPath = '',
  onClose,
  onSelect,
}: RcloneRemoteFolderPickerDialogProps) {
  const { t } = useTranslation()

  return (
    <FileExplorerDialog
      open={open}
      onClose={onClose}
      onSelect={(paths) => onSelect(paths[0] || '')}
      title={t('wizard.cloudMirror.browseTitle')}
      initialPath={initialPath}
      connectionType="rclone"
      rcloneRemoteId={remoteId}
      selectMode="directories"
      multiSelect={false}
    />
  )
}
