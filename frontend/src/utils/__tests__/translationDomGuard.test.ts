import { describe, expect, it } from 'vitest'
import { installTranslationDomGuard } from '../translationDomGuard'

// A browser translator moves React's text nodes into its own <font> wrappers, so
// React later removes or inserts against a node that is no longer a child
// (dashboard 36c775be4bcfa7b6, dbf8bdeaf0261b31, aa169174d6fa736f, 66475b0e36062aed).
describe('installTranslationDomGuard', () => {
  installTranslationDomGuard()
  installTranslationDomGuard()

  it('removes a moved node from where it is now', () => {
    const parent = document.createElement('div')
    const text = parent.appendChild(document.createTextNode('stale'))
    const font = parent.appendChild(document.createElement('font'))
    font.appendChild(text)

    expect(parent.removeChild(text)).toBe(text)
    expect(text.parentNode).toBeNull()
  })

  it('ignores removing a node a translator already dropped', () => {
    const parent = document.createElement('div')
    const text = document.createTextNode('gone')

    expect(parent.removeChild(text)).toBe(text)
  })

  it('inserts before the wrapper that holds the reference', () => {
    const parent = document.createElement('div')
    const reference = document.createTextNode('ref')
    const font = parent.appendChild(document.createElement('font'))
    font.appendChild(reference)
    const trailing = parent.appendChild(document.createElement('button'))
    const added = document.createElement('span')

    expect(parent.insertBefore(added, reference)).toBe(added)
    expect(Array.from(parent.childNodes)).toEqual([added, font, trailing])
  })

  it('appends when the reference was moved out of the parent', () => {
    const parent = document.createElement('div')
    const moved = document.createTextNode('old')
    document.createElement('font').appendChild(moved)
    const added = document.createElement('span')

    expect(parent.insertBefore(added, moved)).toBe(added)
    expect(parent.lastChild).toBe(added)
  })

  it('still removes and inserts real children', () => {
    const parent = document.createElement('div')
    const first = parent.appendChild(document.createElement('span'))
    const added = document.createElement('b')

    parent.insertBefore(added, first)
    expect(parent.firstChild).toBe(added)
    parent.removeChild(first)
    expect(parent.childNodes).toHaveLength(1)
  })
})
