import { Box } from '@mui/material'
import { keyframes } from '@mui/system'

/* The borgui.com sale bar motif: Borg's deduplicated chunks drifting down
   once. Fills its nearest position: relative ancestor and never takes clicks.
   Reduced-motion users never see it. */

const CHUNK_COLORS = ['#34d399', '#f59e0b', '#7c5cfc', '#fb7185']
const CHUNKS = 16

const fall = keyframes`
  0% { transform: translate3d(0, -12px, 0) rotate(0deg); opacity: 0; }
  15% { opacity: 0.9; }
  85% { opacity: 0.7; }
  100% { transform: translate3d(14px, var(--chunk-fall), 0) rotate(220deg); opacity: 0; }
`

interface ChunkBurstProps {
  /** How far the chunks drop, in px. */
  fall?: number
  /** Fade the chunks out towards the bottom so they never sit on body text. */
  fade?: boolean
}

export default function ChunkBurst({ fall: distance = 72, fade = false }: ChunkBurstProps) {
  return (
    <Box
      aria-hidden="true"
      data-testid="chunk-burst"
      sx={{
        position: 'absolute',
        inset: 0,
        overflow: 'hidden',
        pointerEvents: 'none',
        '--chunk-fall': `${distance}px`,
        ...(fade && {
          maskImage: 'linear-gradient(to bottom, #000 0%, #000 35%, transparent 75%)',
        }),
        '@media (prefers-reduced-motion: reduce)': { display: 'none' },
      }}
    >
      {Array.from({ length: CHUNKS }, (_, i) => (
        <Box
          key={i}
          component="span"
          sx={{
            position: 'absolute',
            top: 0,
            left: `${(i * 61) % 100}%`,
            width: i % 4 === 1 ? 6 : i % 4 === 3 ? 5 : 7,
            height: i % 4 === 1 ? 6 : i % 4 === 3 ? 5 : 7,
            borderRadius: i % 3 === 0 ? '50%' : '1.5px',
            bgcolor: CHUNK_COLORS[i % CHUNK_COLORS.length],
            opacity: 0,
            animation: `${fall} ${2.2 + (i % 5) * 0.35}s ease-in ${(i * 0.13) % 1.6}s 1 both`,
          }}
        />
      ))}
    </Box>
  )
}
