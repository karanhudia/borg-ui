import { Box, Divider, Menu, MenuItem, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { formatBytes, formatCalendarDay, parseBackendDate } from '../../utils/dateUtils'

export interface ArchivePickerRow {
  id: number
  name?: string
  start?: string
  size?: number | null
}

interface ArchivePickerMenuProps {
  anchorEl: HTMLElement | null
  /** Any timestamp or yyyy-mm-dd on the day the archives belong to. */
  date: string
  archives: ArchivePickerRow[]
  onPick: (id: number) => void
  onClose: () => void
}

/** Picks one archive out of a heatmap cell that holds several. */
export default function ArchivePickerMenu({
  anchorEl,
  date,
  archives,
  onPick,
  onClose,
}: ArchivePickerMenuProps) {
  const { t } = useTranslation()

  return (
    <Menu
      open={anchorEl != null}
      anchorEl={anchorEl}
      onClose={onClose}
      slotProps={{
        paper: {
          sx: { width: 'min(400px, calc(100vw - 32px))', maxHeight: 400 },
        },
        list: { dense: true, sx: { py: 0 } },
      }}
    >
      <Typography
        component="li"
        variant="caption"
        sx={{ display: 'block', px: 2, py: 1, color: 'text.secondary', fontWeight: 600 }}
      >
        {t('archives.heatmap.pickArchive', {
          count: archives.length,
          date: formatCalendarDay(date),
        })}
      </Typography>
      <Divider component="li" />
      {archives.map((archive) => (
        <MenuItem
          key={archive.id}
          onClick={() => onPick(archive.id)}
          title={archive.name}
          sx={{ gap: 1.5, py: 0.75, alignItems: 'flex-start' }}
        >
          <Typography
            variant="body2"
            sx={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}
          >
            {archive.start
              ? parseBackendDate(archive.start).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })
              : `#${archive.id}`}
          </Typography>
          <Box
            component="span"
            sx={{
              flex: 1,
              minWidth: 0,
              // Plan names share a long prefix and differ in the middle, so two
              // lines show what one line would cut.
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
              wordBreak: 'break-word',
              whiteSpace: 'normal',
              lineHeight: 1.4,
              fontSize: '0.8rem',
              color: 'text.secondary',
            }}
          >
            {archive.name}
          </Box>
          {archive.size != null && (
            <Typography
              variant="caption"
              sx={{ flexShrink: 0, color: 'text.secondary', fontVariantNumeric: 'tabular-nums' }}
            >
              {formatBytes(archive.size)}
            </Typography>
          )}
        </MenuItem>
      ))}
    </Menu>
  )
}
