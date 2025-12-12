import React from 'react'
import { Box, Stack, Typography, Tooltip } from '@mui/material'
import { HardDrive } from 'lucide-react'

interface RepositoryCellProps {
  repositoryName?: string | null
  repositoryPath?: string | null
  withIcon?: boolean
}

/**
 * Standardized repository display component used across Activity, Schedule, and Dashboard views
 * Shows repository name (bold) + truncated path (gray, monospace) with full path in tooltip
 * Matches the design pattern from Dashboard component
 */
export const RepositoryCell: React.FC<RepositoryCellProps> = ({
  repositoryName,
  repositoryPath,
  withIcon = true,
}) => {
  const displayName = repositoryName || repositoryPath || 'Unknown'
  const displayPath = repositoryPath || ''

  // Extract repository name from path if not provided
  const extractNameFromPath = (path: string): string => {
    if (!path) return 'Unknown'
    const parts = path.split('/')
    return parts[parts.length - 1] || parts[parts.length - 2] || path
  }

  const finalName = repositoryName || extractNameFromPath(repositoryPath || '')

  return (
    <Tooltip title={displayPath || 'No path information'} placement="top" arrow>
      <Stack direction="row" spacing={1} alignItems="flex-start" sx={{ color: 'text.secondary' }}>
        {withIcon && <HardDrive size={16} style={{ flexShrink: 0, marginTop: 2 }} />}
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography variant="body2" fontWeight={500} sx={{ wordBreak: 'break-word' }}>
            {finalName}
          </Typography>
          {displayPath && (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                fontFamily: 'monospace',
                fontSize: '0.7rem',
                maxWidth: 250,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                display: 'block',
              }}
            >
              {displayPath}
            </Typography>
          )}
        </Box>
      </Stack>
    </Tooltip>
  )
}

export default RepositoryCell
