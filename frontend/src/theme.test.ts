import { describe, expect, it } from 'vitest'
import { decomposeColor, getContrastRatio } from '@mui/material/styles'
import { blend } from '@mui/system'
import { getTheme } from './theme'

// Components draw palette mains as text on the page, on paper, and on the
// main's own tint (chips, stat tiles, badges), and fill buttons with them
// under contrastText. WCAG AA asks 4.5:1 for all of that.
const AA = 4.5
const TONES = ['primary', 'secondary', 'success', 'error', 'warning', 'info'] as const

// getContrastRatio ignores alpha, so a translucent token would be measured
// as if it were opaque and pass while rendering lighter.
const alphaOf = (color: string) => decomposeColor(color).values[3] ?? 1

describe.each(['light', 'dark'] as const)('%s theme palette contrast', (mode) => {
  const { palette } = getTheme(mode)
  const surfaces = [palette.background.default, palette.background.paper]

  it.each(TONES)('%s.main reads as text on surfaces and on its own tint', (tone) => {
    const { main, contrastText } = palette[tone]
    expect(alphaOf(main), `${tone}.main is opaque`).toBe(1)
    for (const surface of surfaces) {
      expect(getContrastRatio(main, surface), `${tone} on ${surface}`).toBeGreaterThanOrEqual(AA)
      const tint = blend(surface, main, 0.16)
      expect(getContrastRatio(main, tint), `${tone} on 16% tint`).toBeGreaterThanOrEqual(AA)
    }
    expect(getContrastRatio(contrastText, main), `${tone} contrastText`).toBeGreaterThanOrEqual(AA)
  })

  it('keeps secondary and disabled text readable on paper and chip fills', () => {
    const chipFill = blend(palette.background.paper, palette.text.primary, 0.1)
    for (const text of [palette.text.secondary, palette.text.disabled]) {
      expect(alphaOf(text), `${text} is opaque`).toBe(1)
      for (const surface of [...surfaces, chipFill]) {
        expect(getContrastRatio(text, surface), `${text} on ${surface}`).toBeGreaterThanOrEqual(AA)
      }
    }
  })
})
