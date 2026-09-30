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

  it('returns false when no copy method works', async () => {
    setClipboard({ writeText: vi.fn().mockRejectedValue(new Error('denied')) })
    document.execCommand = vi.fn(() => false)

    expect(await copyText('x')).toBe(false)
  })
})
