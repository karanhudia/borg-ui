import { describe, it, expect, vi, afterEach } from 'vitest'
import { copyText } from '../clipboard'

const setClipboard = (value: unknown) =>
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value })

describe('copyText', () => {
  afterEach(() => {
    setClipboard(undefined)
    vi.restoreAllMocks()
  })

  it('uses navigator.clipboard when present', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    setClipboard({ writeText })

    expect(await copyText('hello')).toBe(true)
    expect(writeText).toHaveBeenCalledWith('hello')
  })

  it('falls back to execCommand when navigator.clipboard is missing', async () => {
    setClipboard(undefined)
    let copied: string | undefined
    document.execCommand = vi.fn(() => {
      copied = (document.activeElement as HTMLTextAreaElement).value
      return true
    })

    expect(await copyText('over plain http')).toBe(true)
    expect(document.execCommand).toHaveBeenCalledWith('copy')
    expect(copied).toBe('over plain http')
    expect(document.querySelector('textarea')).toBeNull()
  })

  it('keeps the fallback inside a focus trap such as an MUI dialog', async () => {
    setClipboard(undefined)
    const dialog = document.createElement('div')
    dialog.tabIndex = -1
    const button = document.createElement('button')
    dialog.appendChild(button)
    document.body.appendChild(dialog)
    button.focus()
    // Mimic MUI FocusTrap: pull focus back when it lands outside the dialog.
    const contain = () => {
      if (!dialog.contains(document.activeElement)) dialog.focus()
    }
    document.addEventListener('focusin', contain)
    let copied: string | undefined
    document.execCommand = vi.fn(() => {
      copied = (document.activeElement as HTMLTextAreaElement).value
      return true
    })

    try {
      expect(await copyText('token in a dialog')).toBe(true)
      expect(copied).toBe('token in a dialog')
    } finally {
      document.removeEventListener('focusin', contain)
      dialog.remove()
    }
  })

  it('returns false when no copy method works', async () => {
    setClipboard({ writeText: vi.fn().mockRejectedValue(new Error('denied')) })
    document.execCommand = vi.fn(() => false)

    expect(await copyText('x')).toBe(false)
  })
})
