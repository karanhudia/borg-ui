import { useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Tab,
  Tabs,
  Typography,
} from '@mui/material'
import { Check, Copy } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { copyText } from '../../utils/clipboard'
import ResponsiveDialog from '../shared/ResponsiveDialog'
import { buildClientSnippets } from './clientSnippets'

interface McpConnectedDialogProps {
  open: boolean
  token: string
  endpointUrl: string
  onClose: () => void
}

const codeSx = {
  m: 0,
  p: 1.5,
  borderRadius: 1.5,
  border: '1px solid',
  borderColor: 'divider',
  bgcolor: 'action.hover',
  fontFamily: 'monospace',
  fontSize: '0.8125rem',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-all',
  overflowX: 'auto',
} as const

/** The token, once, and how to connect each client. */
export default function McpConnectedDialog({
  open,
  token,
  endpointUrl,
  onClose,
}: McpConnectedDialogProps) {
  const { t } = useTranslation()
  const snippets = useMemo(() => buildClientSnippets(endpointUrl, token), [endpointUrl, token])
  const [tab, setTab] = useState(0)
  const [copied, setCopied] = useState<string | null>(null)
  const [tokenCopied, setTokenCopied] = useState(false)
  const [confirmClose, setConfirmClose] = useState(false)

  const copy = async (key: string, text: string) => {
    if (!(await copyText(text))) {
      toast.error(t('common.errors.copyFailed'))
      return
    }
    // Copying a snippet copies the token inside it too.
    setTokenCopied(true)
    setCopied(key)
    setTimeout(() => setCopied((current) => (current === key ? null : current)), 2000)
  }

  const requestClose = () => (tokenCopied ? onClose() : setConfirmClose(true))
  const snippet = snippets[tab]

  return (
    <>
      <ResponsiveDialog
        open={open}
        onClose={requestClose}
        maxWidth="md"
        fullWidth
        footer={
          <DialogActions sx={{ px: 3, pb: 2 }}>
            <Button variant="contained" onClick={requestClose}>
              {t('mcp.connected.done')}
            </Button>
          </DialogActions>
        }
      >
        <DialogTitle>{t('mcp.connected.title')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2.5} sx={{ pt: 1 }}>
            <Alert severity="warning">{t('mcp.connected.once')}</Alert>
            <Stack spacing={1}>
              <Typography variant="subtitle2">{t('mcp.connected.tokenLabel')}</Typography>
              <Box sx={{ display: 'flex', gap: 1, alignItems: 'stretch', flexWrap: 'wrap' }}>
                <Box component="code" sx={{ ...codeSx, flex: 1, minWidth: 0 }}>
                  {token}
                </Box>
                <Button
                  variant="outlined"
                  onClick={() => copy('token', token)}
                  startIcon={copied === 'token' ? <Check size={16} /> : <Copy size={16} />}
                  sx={{ minHeight: 44 }}
                >
                  {copied === 'token' ? t('mcp.connected.copied') : t('mcp.connected.copyToken')}
                </Button>
              </Box>
            </Stack>
            <Stack spacing={1}>
              <Typography variant="subtitle2">{t('mcp.connected.connectTitle')}</Typography>
              <Tabs
                value={tab}
                onChange={(_, next) => setTab(next)}
                variant="scrollable"
                allowScrollButtonsMobile
              >
                {snippets.map((s) => (
                  <Tab key={s.id} label={s.label ?? t('mcp.connected.generic')} />
                ))}
              </Tabs>
              <Typography variant="body2" color="text.secondary">
                {snippet.id === 'generic'
                  ? t('mcp.connected.genericHint')
                  : snippet.where
                    ? t('mcp.connected.pasteInto', { file: snippet.where })
                    : t('mcp.connected.runInTerminal')}
              </Typography>
              <Box component="pre" sx={codeSx}>
                {snippet.code}
              </Box>
              <Box>
                <Button
                  size="small"
                  onClick={() => copy(snippet.id, snippet.code)}
                  startIcon={copied === snippet.id ? <Check size={16} /> : <Copy size={16} />}
                  sx={{ minHeight: 44 }}
                >
                  {copied === snippet.id
                    ? t('mcp.connected.copied')
                    : t('mcp.connected.copySnippet')}
                </Button>
              </Box>
            </Stack>
          </Stack>
        </DialogContent>
      </ResponsiveDialog>
      <ResponsiveDialog
        open={confirmClose}
        onClose={() => setConfirmClose(false)}
        maxWidth="xs"
        fullWidth
        footer={
          <DialogActions sx={{ px: 3, pb: 2 }}>
            <Button onClick={() => setConfirmClose(false)}>{t('mcp.connected.keepOpen')}</Button>
            <Button
              color="error"
              onClick={() => {
                setConfirmClose(false)
                onClose()
              }}
            >
              {t('mcp.connected.closeAnyway')}
            </Button>
          </DialogActions>
        }
      >
        <DialogTitle>{t('mcp.connected.closeConfirmTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">{t('mcp.connected.closeConfirmBody')}</Typography>
        </DialogContent>
      </ResponsiveDialog>
    </>
  )
}
