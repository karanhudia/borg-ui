import { Chip } from '@mui/material'
import { KeyRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import RichSelect, { type RichSelectOption } from './RichSelect'

export interface SshKeyOptionSummary {
  id: number
  name: string
  key_type: string
  fingerprint?: string | null
  is_system_key?: boolean
}

interface SshKeySelectProps {
  value: number | ''
  onChange: (id: number) => void
  keys: SshKeyOptionSummary[]
  /** Defaults to "SSH key". */
  label?: string
  labelId?: string
  disabled?: boolean
}

export default function SshKeySelect({
  value,
  onChange,
  keys,
  label,
  labelId,
  disabled,
}: SshKeySelectProps) {
  const { t } = useTranslation()

  const options: RichSelectOption[] = keys.map((key) => ({
    value: String(key.id),
    icon: <KeyRound size={16} />,
    primary: key.name,
    secondary: [key.key_type.toUpperCase(), key.fingerprint].filter(Boolean).join(' • '),
    indicator: key.is_system_key ? (
      <Chip
        size="small"
        variant="outlined"
        label={t('sshConnections.extraKeys.picker.system')}
        sx={{ height: 20, fontSize: '0.65rem' }}
      />
    ) : undefined,
  }))

  return (
    <RichSelect
      value={value === '' ? '' : String(value)}
      onChange={(next) => {
        if (next) onChange(Number(next))
      }}
      options={options}
      label={label ?? t('sshConnections.extraKeys.picker.label')}
      labelId={labelId}
      disabled={disabled}
    />
  )
}
