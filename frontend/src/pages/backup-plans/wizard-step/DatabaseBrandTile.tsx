import { Box, Card, CardActionArea, Stack, Typography, alpha } from '@mui/material'
import { SiMariadb, SiMongodb, SiMysql, SiPostgresql, SiRedis, SiSqlite } from 'react-icons/si'
import type { IconType } from 'react-icons'

import type { SourceDiscoveryDatabase } from '../../../services/api'

interface DatabaseBrand {
  Icon: IconType
  color: string
}

const DATABASE_BRANDS: Record<string, DatabaseBrand> = {
  postgresql: { Icon: SiPostgresql, color: '#336791' },
  mysql: { Icon: SiMysql, color: '#00758F' },
  mariadb: { Icon: SiMariadb, color: '#003545' },
  'mysql / mariadb': { Icon: SiMysql, color: '#00758F' },
  mongodb: { Icon: SiMongodb, color: '#00684A' },
  redis: { Icon: SiRedis, color: '#FF4438' },
  sqlite: { Icon: SiSqlite, color: '#003B57' },
}

function brandFor(engine: string): DatabaseBrand {
  const normalised = engine.trim().toLowerCase()
  if (DATABASE_BRANDS[normalised]) return DATABASE_BRANDS[normalised]
  const key = Object.keys(DATABASE_BRANDS).find((name) => normalised.includes(name))
  if (key) return DATABASE_BRANDS[key]
  return { Icon: SiPostgresql, color: '#5C6B7A' }
}

interface DatabaseBrandTileProps {
  database: SourceDiscoveryDatabase
  detectedLabel: string
  onClick: () => void
}

export function DatabaseBrandTile({ database, detectedLabel, onClick }: DatabaseBrandTileProps) {
  const brand = brandFor(database.engine)
  const BrandIcon = brand.Icon

  return (
    <Card
      variant="outlined"
      sx={{
        borderRadius: 1,
        transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
        '&:hover': {
          transform: 'translateY(-2px)',
          boxShadow: (theme) => `0 2px 6px ${alpha(theme.palette.text.primary, 0.08)}`,
          borderColor: 'text.primary',
        },
      }}
    >
      <CardActionArea
        component="button"
        onClick={onClick}
        sx={{ height: '100%', p: 1.25, display: 'flex', justifyContent: 'flex-start' }}
      >
        <Stack
          direction="row"
          spacing={1.25}
          alignItems="center"
          sx={{ width: '100%', minWidth: 0 }}
        >
          <Box
            sx={{
              alignItems: 'center',
              bgcolor: brand.color,
              borderRadius: 1.5,
              boxShadow: `0 4px 12px ${alpha(brand.color, 0.35)}`,
              color: 'common.white',
              display: 'flex',
              height: 36,
              justifyContent: 'center',
              width: 36,
              flexShrink: 0,
            }}
            aria-hidden
          >
            <BrandIcon size={20} />
          </Box>
          <Stack spacing={0.25} sx={{ minWidth: 0, textAlign: 'left' }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, lineHeight: 1.2 }} noWrap>
              {database.engine}
            </Typography>
            {database.detected && (
              <Stack direction="row" spacing={0.5} alignItems="center">
                <Box
                  sx={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    bgcolor: 'success.main',
                    flexShrink: 0,
                  }}
                />
                <Typography variant="caption" color="success.main" sx={{ fontWeight: 500 }} noWrap>
                  {detectedLabel}
                </Typography>
              </Stack>
            )}
          </Stack>
        </Stack>
      </CardActionArea>
    </Card>
  )
}
