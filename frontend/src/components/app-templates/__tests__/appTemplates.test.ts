import { describe, expect, it } from 'vitest'

import type { AppTemplate } from '../../../services/api'
import {
  appExcludePatterns,
  checksBackedUpDumps,
  defaultAppExcludes,
  isStale,
  mountHint,
  readAccessCommands,
  renderAppScript,
} from '../appTemplates'

const immich = {
  id: 'immich',
  folders: [
    { path: 'upload', role: 'data' },
    { path: 'backups', role: 'database' },
    { path: 'thumbs', role: 'rebuildable' },
    { path: 'encoded-video', role: 'rebuildable' },
  ],
  pre_backup_script: {
    name: 'check',
    description: '',
    timeout: 60,
    content: 'APP_ROOT=__APP_ROOT__\nls "$APP_ROOT/backups"\n',
  },
} as unknown as AppTemplate

describe('app templates', () => {
  it('builds absolute excludes under the root, ignoring a trailing slash', () => {
    expect(appExcludePatterns('/local/srv/immich/', ['thumbs', 'encoded-video'])).toEqual([
      '/local/srv/immich/thumbs',
      '/local/srv/immich/encoded-video',
    ])
  })

  it('skips only rebuildable folders by default', () => {
    expect(defaultAppExcludes(immich)).toEqual(['thumbs', 'encoded-video'])
  })

  it('fills the root into the script, shell-quoted', () => {
    expect(renderAppScript(immich, "/srv/it's here/")).toBe(
      "APP_ROOT='/srv/it'\\''s here'\nls \"$APP_ROOT/backups\"\n"
    )
  })

  it('returns no script when the template has none', () => {
    expect(renderAppScript({ ...immich, pre_backup_script: null }, '/x')).toBeNull()
  })

  it('suggests a read-only mount under /local', () => {
    expect(mountHint('/srv/immich')).toBe('- /srv/immich:/local/srv/immich:ro')
  })

  it('flags a dump older than the allowed age, or none at all', () => {
    const now = Date.parse('2026-09-30T12:00:00Z')
    expect(isStale('2026-09-30T02:00:00Z', 26, now)).toBe(false)
    expect(isStale('2026-09-29T02:00:00Z', 26, now)).toBe(true)
    expect(isStale(null, 26, now)).toBe(true)
    expect(isStale(null, null, now)).toBe(false)
  })

  it('grants read on the folder and only traverse on its parents', () => {
    expect(readAccessCommands('backup', '/home/docker/volumes/abc/_data/')).toBe(
      [
        "sudo setfacl -m u:backup:x '/home' '/home/docker' '/home/docker/volumes' '/home/docker/volumes/abc'",
        "sudo setfacl -R -m u:backup:rX,d:u:backup:rX '/home/docker/volumes/abc/_data'",
      ].join('\n')
    )
  })

  it('drops the dump check when the dumps are not backed up', () => {
    expect(checksBackedUpDumps(immich, ['thumbs'])).toBe(true)
    expect(checksBackedUpDumps(immich, ['backups'])).toBe(false)
  })
})
