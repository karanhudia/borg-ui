import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider, useTheme } from '../ThemeContext'

interface MatchMediaController {
  matches: boolean
  trigger: (matches: boolean) => void
}

function installMatchMedia(initialMatches: boolean): MatchMediaController {
  let listener: ((event: MediaQueryListEvent) => void) | null = null

  const mediaQueryList = {
    matches: initialMatches,
    media: '(prefers-color-scheme: dark)',
    onchange: null,
    addEventListener: vi.fn((_event: string, cb: (event: MediaQueryListEvent) => void) => {
      listener = cb
    }),
    removeEventListener: vi.fn(() => {
      listener = null
    }),
    addListener: vi.fn((cb: (event: MediaQueryListEvent) => void) => {
      listener = cb
    }),
    removeListener: vi.fn(() => {
      listener = null
    }),
    dispatchEvent: vi.fn(),
  }

  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation(() => mediaQueryList)
  )

  return {
    get matches() {
      return mediaQueryList.matches
    },
    trigger(matches: boolean) {
      mediaQueryList.matches = matches
      listener?.({ matches } as MediaQueryListEvent)
    },
  }
}

function ThemeProbe() {
  const { mode, effectiveMode, toggleTheme, setTheme } = useTheme()

  return (
    <div>
      <div data-testid="mode">{mode}</div>
      <div data-testid="effective-mode">{effectiveMode}</div>
      <button type="button" onClick={toggleTheme}>
        toggle
      </button>
      <button type="button" onClick={() => setTheme('auto')}>
        auto
      </button>
      <button type="button" onClick={() => setTheme('light')}>
        light
      </button>
      <button type="button" onClick={() => setTheme('dark')}>
        dark
      </button>
    </div>
  )
}

describe('ThemeContext', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  it('defaults to auto mode and resolves from system preference', () => {
    installMatchMedia(true)

    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>
    )

    expect(screen.getByTestId('mode')).toHaveTextContent('auto')
    expect(screen.getByTestId('effective-mode')).toHaveTextContent('dark')
    expect(localStorage.getItem('theme')).toBe('auto')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('honors an explicitly saved theme over system preference', () => {
    localStorage.setItem('theme', 'light')
    installMatchMedia(true)

    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>
    )

    expect(screen.getByTestId('mode')).toHaveTextContent('light')
    expect(screen.getByTestId('effective-mode')).toHaveTextContent('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('updates effective mode when system theme changes in auto mode', () => {
    const matchMedia = installMatchMedia(false)

    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>
    )

    expect(screen.getByTestId('effective-mode')).toHaveTextContent('light')

    act(() => {
      matchMedia.trigger(true)
    })

    expect(screen.getByTestId('mode')).toHaveTextContent('auto')
    expect(screen.getByTestId('effective-mode')).toHaveTextContent('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('cycles toggleTheme through auto, light, and dark', () => {
    installMatchMedia(false)

    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>
    )

    act(() => {
      screen.getByRole('button', { name: 'toggle' }).click()
    })
    expect(screen.getByTestId('mode')).toHaveTextContent('light')

    act(() => {
      screen.getByRole('button', { name: 'toggle' }).click()
    })
    expect(screen.getByTestId('mode')).toHaveTextContent('dark')

    act(() => {
      screen.getByRole('button', { name: 'toggle' }).click()
    })
    expect(screen.getByTestId('mode')).toHaveTextContent('auto')
  })
})
