import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Typography,
  Button,
  IconButton,
  TextField,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tooltip,
  CircularProgress,
  Alert,
} from '@mui/material'
import { Plus, Trash2, Key, Copy, Check } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { tokensAPI } from '../services/api'
import { formatDateShort } from '../utils/dateUtils'
import EmptyStateCard from './EmptyStateCard'

interface Token {
  id: number
  name: string
  prefix: string
  created_at: string
  last_used_at: string | null
}

export default function ApiTokensSection() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [generateOpen, setGenerateOpen] = useState(false)
  const [tokenName, setTokenName] = useState('')
  const [newToken, setNewToken] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [closeConfirmOpen, setCloseConfirmOpen] = useState(false)

  const { data: tokensData, isLoading } = useQuery({
    queryKey: ['api-tokens'],
    queryFn: () => tokensAPI.list().then((r) => r.data),
  })

  const generateMutation = useMutation({
    mutationFn: (name: string) => tokensAPI.generate(name).then((r) => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['api-tokens'] })
      setNewToken(data.token)
      setTokenName('')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || t('apiTokens.errors.generate'))
    },
  })

  const revokeMutation = useMutation({
    mutationFn: (id: number) => tokensAPI.revoke(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-tokens'] })
      toast.success(t('apiTokens.revoked'))
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || t('apiTokens.errors.revoke'))
    },
  })

  const handleCopy = async () => {
    if (!newToken) return
    await navigator.clipboard.writeText(newToken)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleCloseCopyModal = () => {
    if (!copied) {
      setCloseConfirmOpen(true)
    } else {
      setNewToken(null)
      setGenerateOpen(false)
    }
  }

  const tokens: Token[] = tokensData ?? []

  return (
    <Box>
      <Box
        sx={{
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 2,
          overflow: 'hidden',
          mb: 0,
        }}
      >
        <Box
          sx={{
            px: 2.5,
            py: 2,
            borderBottom: '1px solid',
            borderColor: 'divider',
            bgcolor: 'action.hover',
            display: 'flex',
            flexDirection: { xs: 'column', sm: 'row' },
            justifyContent: 'space-between',
            alignItems: { xs: 'flex-start', sm: 'center' },
            gap: { xs: 1.5, sm: 0 },
          }}
        >
          <Box>
            <Typography
              variant="body2"
              sx={{
                fontWeight: 600,
              }}
            >
              {t('apiTokens.title')}
            </Typography>
            <Typography
              variant="caption"
              sx={{
                color: 'text.secondary',
              }}
            >
              {t('apiTokens.description')}
            </Typography>
          </Box>
          <Button
            variant="outlined"
            size="small"
            startIcon={<Plus size={14} />}
            onClick={() => setGenerateOpen(true)}
            sx={{ width: { xs: '100%', sm: 'auto' } }}
          >
            {t('common.buttons.generate')}
          </Button>
        </Box>

        <Box>
          {isLoading ? (
            <Box sx={{ p: 3, display: 'flex', justifyContent: 'center' }}>
              <CircularProgress size={24} />
            </Box>
          ) : tokens.length === 0 ? (
            <EmptyStateCard inline icon={<Key size={32} />} title={t('apiTokens.empty')} />
          ) : (
            <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse' }}>
              <Box component="thead">
                <Box component="tr" sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
                  {[
                    t('common.name'),
                    t('apiTokens.prefix'),
                    t('apiTokens.created'),
                    t('apiTokens.lastUsed'),
                    '',
                  ].map((h) => (
                    <Box
                      key={h}
                      component="th"
                      sx={{
                        p: 1.5,
                        textAlign: 'left',
                        typography: 'caption',
                        fontWeight: 700,
                        color: 'text.secondary',
                      }}
                    >
                      {h}
                    </Box>
                  ))}
                </Box>
              </Box>
              <Box component="tbody">
                {tokens.map((token) => (
                  <Box
                    key={token.id}
                    component="tr"
                    sx={{
                      '&:not(:last-child)': { borderBottom: '1px solid', borderColor: 'divider' },
                    }}
                  >
                    <Box component="td" sx={{ p: 1.5 }}>
                      <Typography
                        variant="body2"
                        sx={{
                          fontWeight: 500,
                        }}
                      >
                        {token.name}
                      </Typography>
                    </Box>
                    <Box component="td" sx={{ p: 1.5 }}>
                      <Typography
                        variant="body2"
                        sx={{
                          fontFamily: 'monospace',
                          fontSize: '0.8rem',
                          color: 'text.secondary',
                        }}
                      >
                        {token.prefix}…
                      </Typography>
                    </Box>
                    <Box component="td" sx={{ p: 1.5 }}>
                      <Typography variant="body2">{formatDateShort(token.created_at)}</Typography>
                    </Box>
                    <Box component="td" sx={{ p: 1.5 }}>
                      <Typography
                        variant="body2"
                        sx={{
                          color: 'text.secondary',
                        }}
                      >
                        {token.last_used_at
                          ? formatDateShort(token.last_used_at)
                          : t('common.never')}
                      </Typography>
                    </Box>
                    <Box component="td" sx={{ p: 1.5, textAlign: 'right' }}>
                      <Tooltip title={t('apiTokens.revoke')}>
                        <IconButton
                          size="small"
                          color="error"
                          onClick={() => revokeMutation.mutate(token.id)}
                          disabled={revokeMutation.isPending}
                        >
                          <Trash2 size={16} />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  </Box>
                ))}
              </Box>
            </Box>
          )}
        </Box>
      </Box>

      {/* Generate Token Dialog */}
      <Dialog
        open={generateOpen && !newToken}
        onClose={() => setGenerateOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('apiTokens.generateTitle')}</DialogTitle>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            generateMutation.mutate(tokenName)
          }}
        >
          <DialogContent>
            <TextField
              label={t('apiTokens.name')}
              value={tokenName}
              onChange={(e) => setTokenName(e.target.value)}
              placeholder={t('apiTokens.namePlaceholder')}
              required
              fullWidth
              autoFocus
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setGenerateOpen(false)}>{t('common.buttons.cancel')}</Button>
            <Button
              type="submit"
              variant="contained"
              disabled={generateMutation.isPending || !tokenName.trim()}
            >
              {generateMutation.isPending ? (
                <CircularProgress size={16} />
              ) : (
                t('common.buttons.generate')
              )}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* One-time token copy dialog */}
      <Dialog open={!!newToken} onClose={handleCloseCopyModal} maxWidth="sm" fullWidth>
        <DialogTitle>{t('apiTokens.newTokenTitle')}</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            {t('apiTokens.copyWarning')}
          </Alert>
          <Stack
            direction="row"
            spacing={1}
            sx={{
              alignItems: 'center',
            }}
          >
            <TextField
              value={newToken ?? ''}
              fullWidth
              onClick={(e) => (e.target as HTMLInputElement).select()}
              slotProps={{
                input: { readOnly: true, sx: { fontFamily: 'monospace', fontSize: '0.8rem' } },
              }}
            />
            <Tooltip title={copied ? t('apiTokens.copied') : t('apiTokens.copyToClipboard')}>
              <IconButton onClick={handleCopy} color={copied ? 'success' : 'default'}>
                {copied ? <Check size={18} /> : <Copy size={18} />}
              </IconButton>
            </Tooltip>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseCopyModal} variant="contained">
            {t('common.buttons.finish')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Confirm close without copying */}
      <Dialog
        open={closeConfirmOpen}
        onClose={() => setCloseConfirmOpen(false)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>{t('apiTokens.closeWithoutCopyingTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">{t('apiTokens.closeWithoutCopyingDescription')}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCloseConfirmOpen(false)}>{t('common.buttons.back')}</Button>
          <Button
            color="error"
            onClick={() => {
              setNewToken(null)
              setCloseConfirmOpen(false)
              setGenerateOpen(false)
            }}
          >
            {t('apiTokens.closeAnyway')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
