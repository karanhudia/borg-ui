import { describe, expect, it } from 'vitest'

import de from '../../locales/de.json'
import en from '../../locales/en.json'
import es from '../../locales/es.json'
import itLocale from '../../locales/it.json'
import i18n from '../../i18n'
import { translateBackendKey } from '../translateBackendKey'

const locales = { de, en, es, it: itLocale }

const repositoryErrorKeys = [
  'backend.errors.repo.nameExists',
  'backend.errors.repo.pathExists',
  'backend.errors.repo.initFailed',
  'backend.errors.repo.verificationFailed',
  'backend.errors.repo.infoFailed',
  'backend.errors.repo.listFailed',
  'backend.errors.repo.failedToInitializeRepository',
  'backend.errors.repo.remoteBorg2Incompatible',
  'backend.errors.repo.borg2OnlyUrl',
  'backend.errors.repo.borg2OnlyUrlOrSshHost',
] as const

const backupPlanErrorKeys = ['backend.errors.backupPlans.nameExists'] as const

function lookup(locale: unknown, key: string): unknown {
  return key.split('.').reduce<unknown>((value, segment) => {
    if (typeof value !== 'object' || value === null || !(segment in value)) {
      return undefined
    }
    return (value as Record<string, unknown>)[segment]
  }, locale)
}

describe('backend repository translations', () => {
  it('defines repository error keys in every bundled locale', () => {
    for (const [localeName, locale] of Object.entries(locales)) {
      for (const key of repositoryErrorKeys) {
        const value = lookup(locale, key)

        expect(value, `${localeName}:${key}`).toEqual(expect.any(String))
        expect(value, `${localeName}:${key}`).not.toBe(key)
      }
    }
  })

  it('defines backup plan error keys in every bundled locale', () => {
    for (const [localeName, locale] of Object.entries(locales)) {
      for (const key of backupPlanErrorKeys) {
        const value = lookup(locale, key)

        expect(value, `${localeName}:${key}`).toEqual(expect.any(String))
        expect(value, `${localeName}:${key}`).not.toBe(key)
      }
    }
  })

  it('translates duplicate backup plan names', async () => {
    await i18n.changeLanguage('en')

    expect(translateBackendKey({ key: 'backend.errors.backupPlans.nameExists' })).toBe(
      'A backup plan with this name already exists.'
    )
  })

  it('names the scheme of a repository URL only Borg 2 can open', async () => {
    await i18n.changeLanguage('en')

    expect(
      translateBackendKey({
        key: 'backend.errors.repo.borg2OnlyUrl',
        params: { scheme: 'sftp://' },
      })
    ).toBe(
      "A sftp:// repository URL needs Borg 2; Borg 1 can't open it. Pick Borg 2 for this repository."
    )
  })

  it('says how to write an SSH host named like a Borg 2 store', async () => {
    await i18n.changeLanguage('en')

    expect(
      translateBackendKey({
        key: 'backend.errors.repo.borg2OnlyUrlOrSshHost',
        params: { scheme: 's3:', host: 's3' },
      })
    ).toBe(
      'A s3: repository URL needs Borg 2; Borg 1 reads it as an SSH host named s3. Pick Borg 2 for this repository, or write the SSH host as ssh://s3/path (ssh://s3/./path for a path relative to the login directory).'
    )
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

  it('translates legacy repository initialization failures with backend error params', async () => {
    await i18n.changeLanguage('en')

    expect(
      translateBackendKey({
        key: 'backend.errors.repo.failedToInitializeRepository',
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
