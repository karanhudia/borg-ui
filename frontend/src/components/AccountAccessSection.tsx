import { Box, Stack, Typography } from '@mui/material'
import { ShieldCheck } from 'lucide-react'
import ApiTokensSection from './ApiTokensSection'
import UserPermissionsPanel from './UserPermissionsPanel'

interface AccountAccessSectionProps {
  hasGlobalRepositoryAccess: boolean
}

export default function AccountAccessSection({
  hasGlobalRepositoryAccess,
}: AccountAccessSectionProps) {
  return (
    <Stack spacing={3}>
      <Box>
        <Stack direction="row" spacing={1.25} alignItems="center" sx={{ mb: 1 }}>
          <ShieldCheck size={16} style={{ opacity: 0.6 }} />
          <Typography variant="subtitle1" fontWeight={700}>
            Access
          </Typography>
        </Stack>
        <Typography variant="body2" color="text.secondary">
          Tokens and repository access live under the same account umbrella.
        </Typography>
      </Box>
      <ApiTokensSection />
      {!hasGlobalRepositoryAccess ? (
        <UserPermissionsPanel
          title="Repository permissions"
          subtitle="Your current repository-level access."
        />
      ) : (
        <Box
          sx={{
            px: 2.5,
            py: 2,
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 2.5,
            display: 'flex',
            alignItems: 'center',
            gap: 1.5,
            bgcolor: 'action.hover',
          }}
        >
          <ShieldCheck size={16} style={{ color: '#f87171', flexShrink: 0 }} />
          <Box>
            <Typography variant="body2" fontWeight={700}>
              Global access
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Admin accounts inherit full access to all repositories and settings.
            </Typography>
          </Box>
        </Box>
      )}
    </Stack>
  )
}
