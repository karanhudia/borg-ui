/** Shared by every small status chip on an agent card, so they stay identical. */
export const agentChipSx = {
  height: 18,
  fontSize: '0.58rem',
  fontWeight: 600,
  '& .MuiChip-label': { px: 0.75 },
} as const
