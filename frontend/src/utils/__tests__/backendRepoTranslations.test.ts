import { describe, expect, it } from 'vitest'

import de from '../../locales/de.json'
import en from '../../locales/en.json'
import es from '../../locales/es.json'
import itLocale from '../../locales/it.json'
import i18n from '../../i18n'
import { translateBackendKey } from '../translateBackendKey'

const locales = { de, en, es, it: itLocale }

const borg2RepoErrorKeys = [
  'backend.errors.repo.nameExists',
  'backend.errors.repo.pathExists',
  'backend.errors.repo.initFailed',
  'backend.errors.repo.verificationFailed',
  'backend.errors.repo.infoFailed',
  'backend.errors.repo.listFailed',
  'backend.errors.repo.remoteBorg2Incompatible',
] as const

function lookup(locale: unknown, key: string): unknown {
  return key.split('.').reduce<unknown>((value, segment) => {
    if (typeof value !== 'object' || value === null || !(segment in value)) {
      return undefined
    }
    return (value as Record<string, unknown>)[segment]
  }, locale)
}

describe('backend repository translations', () => {
  it('defines Borg 2 repository error keys in every bundled locale', () => {
    for (const [localeName, locale] of Object.entries(locales)) {
      for (const key of borg2RepoErrorKeys) {
        const value = lookup(locale, key)

        expect(value, `${localeName}:${key}`).toEqual(expect.any(String))
        expect(value, `${localeName}:${key}`).not.toBe(key)
      }
    }
  })

  it('translates Borg 2 initialization failures with backend error params', async () => {
    await i18n.changeLanguage('en')

    expect(
      translateBackendKey({
        key: 'backend.errors.repo.initFailed',
        params: { error: 'remote: borg: command not found' },
      })
    ).toBe('Failed to initialize repository: remote: borg: command not found')
  })

  it('translates Borg 2 remote protocol mismatches to a friendly message', async () => {
    await i18n.changeLanguage('en')

    expect(
      translateBackendKey({
        key: 'backend.errors.repo.remoteBorg2Incompatible',
      })
    ).toContain('compatible Borg 2 server')
  })
})
