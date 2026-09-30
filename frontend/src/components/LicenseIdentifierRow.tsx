import { IconButton, Stack, Tooltip, Typography } from '@mui/material'
import { toast } from 'react-hot-toast'
import { Check, Copy } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { copyText } from '../utils/clipboard'

const MONO = '"JetBrains Mono","Fira Code",ui-monospace,monospace'

interface LicenseIdentifierRowProps {
  label: string
  value: string
  /** Identifiers are copied far more often than read out, so they carry a copy
   *  action; plain facts such as an expiry date do not. */
  copyable?: boolean
}

/** One label / value line in the licence card: prose label, mono value. */
export default function LicenseIdentifierRow({
  label,
  value,
  copyable = false,
}: LicenseIdentifierRowProps) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    if (!(await copyText(value))) {
      toast.error(t('common.errors.copyFailed'))
      return
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      spacing={{ xs: 0, sm: 2 }}
      sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between', minHeight: 32 }}
    >
      <Typography variant="body2" sx={{ color: 'text.secondary', flexShrink: 0 }}>
        {label}
      </Typography>
      <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', minWidth: 0 }}>
        <Typography
          variant="body2"
          sx={{ fontFamily: MONO, fontSize: '0.8125rem', wordBreak: 'break-all' }}
        >
          {value}
        </Typography>
        {copyable && (
          <Tooltip title={copied ? t('licensing.copied') : t('licensing.copyValue')}>
            <IconButton size="small" onClick={handleCopy} aria-label={t('licensing.copyValue')}>
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </IconButton>
          </Tooltip>
        )}
      </Stack>
    </Stack>
  )
}
