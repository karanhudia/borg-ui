import { IconButton, Stack, Tooltip, Typography } from '@mui/material'
import { Check, Copy } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

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
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard is unavailable over plain http; the value stays selectable.
    }
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
