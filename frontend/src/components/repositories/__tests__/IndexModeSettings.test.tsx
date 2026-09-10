import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import IndexModeSettings from '../IndexModeSettings'
import type { IndexMode } from '../../../types/operations'

function renderSettings(props: { mode?: IndexMode; excludes?: string[] } = {}) {
  const handlers = { onModeChange: vi.fn(), onExcludesChange: vi.fn() }
  render(<IndexModeSettings mode="full" excludes={[]} {...handlers} {...props} />)
  return handlers
}

describe('IndexModeSettings (spec 6.8, 6.7)', () => {
  it('offers the three modes with their cost line', async () => {
    renderSettings()
    await userEvent.click(screen.getByLabelText(/background indexing/i))
    const options = screen.getAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual([
      expect.stringContaining('Everything'),
      expect.stringContaining('Archives only'),
      expect.stringContaining('Off'),
    ])
    // Every mode says what it costs, per spec 6.8.
    expect(options[1].textContent).toMatch(/stops diffing files/i)
    expect(options[2].textContent).toMatch(/no longer refresh/i)
  })

  it('reports a mode change', async () => {
    const { onModeChange } = renderSettings()
    await userEvent.click(screen.getByLabelText(/background indexing/i))
    await userEvent.click(screen.getByRole('option', { name: /archives only/i }))
    expect(onModeChange).toHaveBeenCalledWith('archives')
  })

  it('parses one pattern per line, trimmed, with blanks dropped', async () => {
    // The field is controlled, so the test has to hold the state the
    // wizard holds in the real app.
    const seen: string[][] = []
    function Harness() {
      const [excludes, setExcludes] = useState<string[]>(['**/.cache/**'])
      return (
        <IndexModeSettings
          mode="full"
          excludes={excludes}
          onModeChange={vi.fn()}
          onExcludesChange={(value) => {
            seen.push(value)
            setExcludes(value)
          }}
        />
      )
    }
    render(<Harness />)
    const field = screen.getByLabelText(/paths to skip/i)
    await userEvent.clear(field)
    await userEvent.type(field, '**/a/**{enter}{enter}  **/b/**  ')
    expect(seen[seen.length - 1]).toEqual(['**/a/**', '**/b/**'])
  })

  it('disables the exclude list when the mode does not index history', () => {
    renderSettings({ mode: 'archives' })
    expect(screen.getByLabelText(/paths to skip/i)).toBeDisabled()
  })
})
