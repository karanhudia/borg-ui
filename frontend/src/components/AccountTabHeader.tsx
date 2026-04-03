import { Box, Card, Chip, Stack, Typography } from '@mui/material'
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
  deploymentLabel,
}: AccountTabHeaderProps) {
  return (
    <Card variant="outlined" sx={{ borderRadius: 3, overflow: 'hidden' }}>
      <Box
        sx={{
          px: { xs: 2.5, md: 3.5 },
          py: { xs: 2.5, md: 3 },
          background: 'linear-gradient(180deg, rgba(23,23,23,0.03) 0%, rgba(23,23,23,0.00) 100%)',
          borderBottom: '1px solid',
          borderColor: 'divider',
        }}
      >
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={2}
          alignItems={{ xs: 'flex-start', sm: 'center' }}
          justifyContent="space-between"
        >
          <Stack direction="row" spacing={2} alignItems="center">
            <Box
              sx={{
                width: 60,
                height: 60,
                borderRadius: 2,
                bgcolor: '#171717',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.25rem',
                fontWeight: 700,
                flexShrink: 0,
              }}
            >
              {username.charAt(0).toUpperCase()}
            </Box>
            <Box>
              <Typography variant="h5" fontWeight={700}>
                {displayName}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {subtitle}
              </Typography>
            </Box>
          </Stack>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip label={roleLabel} color={roleColor} size="small" />
            {deploymentLabel ? (
              <Chip label={deploymentLabel} variant="outlined" size="small" />
            ) : null}
            <Chip label={`@${username}`} variant="outlined" size="small" />
            <Chip
              label={`Member since ${formatDateShort(createdAt)}`}
              variant="outlined"
              size="small"
            />
          </Stack>
        </Stack>
      </Box>
    </Card>
  )
}
