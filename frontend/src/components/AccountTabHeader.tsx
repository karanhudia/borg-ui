import { Box, Chip, Stack, Typography } from '@mui/material'
import { formatDateShort } from '../utils/dateUtils'

interface AccountTabHeaderProps {
  username: string
  displayName: string
  subtitle: string
  roleLabel: string
  roleColor: 'default' | 'secondary' | 'info'
  createdAt: string
  deploymentLabel?: string | null
}

export default function AccountTabHeader({
  username,
  displayName,
  subtitle,
  roleLabel,
  roleColor,
  createdAt,
}: AccountTabHeaderProps) {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: { xs: 'column', sm: 'row' },
        justifyContent: 'space-between',
        alignItems: { xs: 'flex-start', sm: 'center' },
        gap: 1.5,
      }}
    >
      <Box>
        <Typography variant="h6" fontWeight={600}>
          {displayName}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {subtitle}
        </Typography>
      </Box>
      <Stack direction="row" spacing={1} alignItems="center" flexShrink={0}>
        <Chip label={roleLabel} color={roleColor} size="small" />
        <Typography variant="body2" color="text.disabled" sx={{ whiteSpace: 'nowrap' }}>
          @{username} · since {formatDateShort(createdAt)}
        </Typography>
      </Stack>
    </Box>
  )
}
