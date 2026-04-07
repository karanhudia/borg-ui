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
import { tokensAPI } from '../services/api'
import { formatDateShort } from '../utils/dateUtils'

interface Token {
  id: number
  name: string
  prefix: string
  created_at: string
  last_used_at: string | null
}

export default function ApiTokensSection() {
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
      toast.error(error.response?.data?.detail || 'Failed to generate token')
    },
  })

  const revokeMutation = useMutation({
    mutationFn: (id: number) => tokensAPI.revoke(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-tokens'] })
      toast.success('Token revoked')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to revoke token')
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
            <Typography variant="body2" fontWeight={600}>
              API Tokens
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Programmatic access — shown only once when generated
            </Typography>
          </Box>
          <Button
            variant="outlined"
            size="small"
            startIcon={<Plus size={14} />}
            onClick={() => setGenerateOpen(true)}
            sx={{ width: { xs: '100%', sm: 'auto' } }}
          >
            Generate
          </Button>
        </Box>

        <Box>
          {isLoading ? (
            <Box sx={{ p: 3, display: 'flex', justifyContent: 'center' }}>
              <CircularProgress size={24} />
            </Box>
          ) : tokens.length === 0 ? (
            <Box sx={{ p: 3, textAlign: 'center' }}>
              <Key size={32} style={{ opacity: 0.3, marginBottom: 8 }} />
              <Typography variant="body2" color="text.secondary">
                No tokens yet
              </Typography>
            </Box>
          ) : (
            <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse' }}>
              <Box component="thead">
                <Box component="tr" sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
                  {['Name', 'Prefix', 'Created', 'Last used', ''].map((h) => (
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
                      <Typography variant="body2" fontWeight={500}>
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
                      <Typography variant="body2" color="text.secondary">
                        {token.last_used_at ? formatDateShort(token.last_used_at) : 'Never'}
                      </Typography>
                    </Box>
                    <Box component="td" sx={{ p: 1.5, textAlign: 'right' }}>
                      <Tooltip title="Revoke token">
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
        <DialogTitle>Generate API Token</DialogTitle>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            generateMutation.mutate(tokenName)
          }}
        >
          <DialogContent>
            <TextField
              label="Token name"
              value={tokenName}
              onChange={(e) => setTokenName(e.target.value)}
              placeholder="e.g. CI deploy, Home automation"
              required
              fullWidth
              autoFocus
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setGenerateOpen(false)}>Cancel</Button>
            <Button
              type="submit"
              variant="contained"
              disabled={generateMutation.isPending || !tokenName.trim()}
            >
              {generateMutation.isPending ? <CircularProgress size={16} /> : 'Generate'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* One-time token copy dialog */}
      <Dialog open={!!newToken} onClose={handleCloseCopyModal} maxWidth="sm" fullWidth>
        <DialogTitle>Your new API token</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            Copy this token now. You won't be able to see it again.
          </Alert>
          <Stack direction="row" spacing={1} alignItems="center">
            <TextField
              value={newToken ?? ''}
              fullWidth
              InputProps={{ readOnly: true, sx: { fontFamily: 'monospace', fontSize: '0.8rem' } }}
              onClick={(e) => (e.target as HTMLInputElement).select()}
            />
            <Tooltip title={copied ? 'Copied!' : 'Copy to clipboard'}>
              <IconButton onClick={handleCopy} color={copied ? 'success' : 'default'}>
                {copied ? <Check size={18} /> : <Copy size={18} />}
              </IconButton>
            </Tooltip>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseCopyModal} variant="contained">
            Done
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
        <DialogTitle>Close without copying?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            You haven't copied the token. Once you close this dialog, the token cannot be retrieved.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCloseConfirmOpen(false)}>Go back</Button>
          <Button
            color="error"
            onClick={() => {
              setNewToken(null)
              setCloseConfirmOpen(false)
              setGenerateOpen(false)
            }}
          >
            Close anyway
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
