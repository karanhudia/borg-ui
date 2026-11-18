import { describe, expect, it } from 'vitest'
import { installTranslationDomGuard } from '../translationDomGuard'

// A browser translator moves React's text nodes into its own <font> wrappers, so
// React later removes or inserts against a node that is no longer a child
// (dashboard 36c775be4bcfa7b6, dbf8bdeaf0261b31, aa169174d6fa736f, 66475b0e36062aed).
describe('installTranslationDomGuard', () => {
  installTranslationDomGuard()
  installTranslationDomGuard()

  it('ignores removing a node a translator moved away', () => {
    const parent = document.createElement('div')
    const text = document.createTextNode('Repositories')
    parent.appendChild(text)
    const font = document.createElement('font')
    font.appendChild(text)
    parent.appendChild(font)

    expect(parent.removeChild(text)).toBe(text)
    expect(font.firstChild).toBe(text)
  })

  it('appends when the reference node was moved away', () => {
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
