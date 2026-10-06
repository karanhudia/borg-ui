/**
 * Tests for borgUtils.ts
 * Focus: Command generation that must produce valid Borg commands
 * WHY: Invalid commands = backup fails silently until user checks logs
 */

import { describe, it, expect } from 'vitest'
import {
  generateBorgCreateCommand,
  generateBorgInitCommand,
  remotePathParts,
  borg2CanCreateWith,
  isBorg2OnlyUrl,
  borg2PathIsAbsolute,
  borg2PathFromUrlTail,
  borg2SshUrlIsAbsolute,
  borg2SshUrl,
  BorgCommandOptions,
} from './borgUtils'

describe('borg2CanCreateWith', () => {
  it('refuses none, which Borg 2 does not have', () => {
    expect(borg2CanCreateWith('none')).toBe(false)
    expect(borg2CanCreateWith('repokey-aes-ocb')).toBe(true)
    expect(borg2CanCreateWith('authenticated')).toBe(true)
  })
})

describe('remotePathParts', () => {
  it('gives Borg 1 the option and Borg 2 the environment variable', () => {
    // Borg 2 has no --remote-path and reads BORG_REMOTE_PATH
    expect(remotePathParts(1, '/opt/borg')).toEqual({
      flag: '--remote-path /opt/borg ',
      envPrefix: '',
    })
    expect(remotePathParts(2, '/opt/borg')).toEqual({
      flag: '',
      envPrefix: 'BORG_REMOTE_PATH=/opt/borg ',
    })
    expect(remotePathParts(2, '')).toEqual({ flag: '', envPrefix: '' })
  })

  it('quotes a remote command that holds spaces as one shell word', () => {
    expect(remotePathParts(1, 'sudo -n -H /opt/borg').flag).toBe(
      "--remote-path 'sudo -n -H /opt/borg' "
    )
    expect(remotePathParts(2, 'sudo -n -H /opt/borg2').envPrefix).toBe(
      "BORG_REMOTE_PATH='sudo -n -H /opt/borg2' "
    )
  })
})

describe('generateBorgCreateCommand', () => {
  it('generates valid command with all options', () => {
    const options: BorgCommandOptions = {
      repositoryPath: '/backups/repo',
      compression: 'zstd,6',
      excludePatterns: ['*.log', '/tmp/*'],
      sourceDirs: ['/data', '/home'],
      customFlags: '--stats --json',
      archiveName: 'backup-{now}',
    }

    const cmd = generateBorgCreateCommand(options)

    // Verify all components are present
    expect(cmd).toContain('borg create')
    expect(cmd).toContain('--compression zstd,6')
    expect(cmd).toContain("--exclude '*.log'")
    expect(cmd).toContain("--exclude '/tmp/*'")
    expect(cmd).toContain('/backups/repo::backup-{now}')
    expect(cmd).toContain('/data /home')
    expect(cmd).toContain('--stats --json')
    expect(cmd).toContain('--progress')
  })

  it('uses borg2 binary when borgVersion is 2', () => {
    const cmd = generateBorgCreateCommand({
      repositoryPath: '/backups/repo',
      borgVersion: 2,
      sourceDirs: ['/data'],
    })

    expect(cmd).toContain('borg2 -r /backups/repo create')
    expect(cmd).not.toContain('borg create')
  })

  it('passes a Borg 2 repository with -r and the archive name on its own', () => {
    const cmd = generateBorgCreateCommand({
      repositoryPath: '/backups/repo',
      borgVersion: 2,
      compression: 'zstd,6',
      excludePatterns: ['*.tmp'],
      sourceDirs: ['/data', '/etc'],
      archiveName: 'host-{now}',
    })

    // Borg 2 reads repo::archive as an archive name and fails without a repository
    expect(cmd).toBe(
      "borg2 -r /backups/repo create --progress --stats --compression zstd,6 --exclude '*.tmp' host-{now} /data /etc"
    )
  })

  it('generates minimal command with defaults', () => {
    const options: BorgCommandOptions = {
      repositoryPath: '/backups/repo',
    }

    const cmd = generateBorgCreateCommand(options)

    // Check defaults are applied
    expect(cmd).toContain('borg create')
    expect(cmd).toContain('--compression lz4') // default compression
    expect(cmd).toContain('/backups/repo::{hostname}-{now}') // default archive name
    expect(cmd).toContain('/data') // default source dir
    expect(cmd).toContain('--progress')
    expect(cmd).toContain('--stats')
  })

  it('handles empty arrays gracefully', () => {
    const options: BorgCommandOptions = {
      repositoryPath: '/repo',
      excludePatterns: [],
      sourceDirs: ['/data'],
    }

    const cmd = generateBorgCreateCommand(options)

    // Should not have exclude flags
    expect(cmd).not.toContain('--exclude')
    expect(cmd).toContain('/data')
  })

  it('handles multiple source directories', () => {
    const options: BorgCommandOptions = {
      repositoryPath: '/repo',
      sourceDirs: ['/data', '/home', '/var/log', '/etc'],
    }

    const cmd = generateBorgCreateCommand(options)

    expect(cmd).toContain('/data /home /var/log /etc')
  })

  it('handles multiple exclude patterns', () => {
    const options: BorgCommandOptions = {
      repositoryPath: '/repo',
      sourceDirs: ['/data'],
      excludePatterns: ['*.log', '*.tmp', '*.cache', '/tmp/*', '*/node_modules/*'],
    }

    const cmd = generateBorgCreateCommand(options)

    expect(cmd).toContain("--exclude '*.log'")
    expect(cmd).toContain("--exclude '*.tmp'")
    expect(cmd).toContain("--exclude '*.cache'")
    expect(cmd).toContain("--exclude '/tmp/*'")
    expect(cmd).toContain("--exclude '*/node_modules/*'")
  })

  it('includes remote path flag if provided', () => {
    const options: BorgCommandOptions = {
      repositoryPath: '/repo',
      sourceDirs: ['/data'],
      remotePathFlag: '--remote-path /custom/borg ',
    }

    const cmd = generateBorgCreateCommand(options)

    expect(cmd).toContain('--remote-path /custom/borg')
  })

  it('handles custom flags correctly', () => {
    const options: BorgCommandOptions = {
      repositoryPath: '/repo',
      sourceDirs: ['/data'],
      customFlags: '--one-file-system --exclude-caches',
    }

    const cmd = generateBorgCreateCommand(options)

    expect(cmd).toContain('--one-file-system')
    expect(cmd).toContain('--exclude-caches')
  })

  it('handles various compression options', () => {
    const compressionOptions = [
      'lz4',
      'lz4,6',
      'zstd',
      'zstd,10',
      'auto,lz4',
      'auto,zstd,3',
      'obfuscate,110,auto,zstd,3',
      'none',
    ]

    compressionOptions.forEach((compression) => {
      const cmd = generateBorgCreateCommand({
        repositoryPath: '/repo',
        sourceDirs: ['/data'],
        compression,
      })

      expect(cmd).toContain(`--compression ${compression}`)
    })
  })

  it('handles paths with special characters', () => {
    const options: BorgCommandOptions = {
      repositoryPath: '/backups/my-repo',
      sourceDirs: ['/data/user-files', '/home/user_name'],
      excludePatterns: ['*.tmp', '/cache/*'],
    }

    const cmd = generateBorgCreateCommand(options)

    // Verify command is generated correctly
    expect(cmd).toContain('/backups/my-repo::')
    expect(cmd).toContain('/data/user-files')
    expect(cmd).toContain('/home/user_name')
  })

  it('handles SSH repository paths', () => {
    const options: BorgCommandOptions = {
      repositoryPath: 'ssh://user@server.com:22/backups/repo',
      sourceDirs: ['/data'],
    }

    const cmd = generateBorgCreateCommand(options)

    expect(cmd).toContain('ssh://user@server.com:22/backups/repo::')
  })

  it('trims custom flags properly', () => {
    const options: BorgCommandOptions = {
      repositoryPath: '/repo',
      sourceDirs: ['/data'],
      customFlags: '  --stats   --json  ',
    }

    const cmd = generateBorgCreateCommand(options)

    // Should trim outer spaces and preserve inner spacing as user entered
    expect(cmd).toContain('--stats   --json')
    // Command should be generated (custom flags preserved as entered)
    expect(cmd).toContain('borg create')
  })

  it('handles empty custom flags', () => {
    const options: BorgCommandOptions = {
      repositoryPath: '/repo',
      sourceDirs: ['/data'],
      customFlags: '',
    }

    const cmd = generateBorgCreateCommand(options)

    expect(cmd).toContain('borg create')
    // Should still have required flags
    expect(cmd).toContain('--progress')
    expect(cmd).toContain('--stats')
  })

  it('maintains correct flag order', () => {
    const options: BorgCommandOptions = {
      repositoryPath: '/repo',
      compression: 'lz4',
      excludePatterns: ['*.log'],
      sourceDirs: ['/data'],
      customFlags: '--one-file-system',
      archiveName: 'test-{now}',
    }

    const cmd = generateBorgCreateCommand(options)

    // Basic structure check: borg create [flags] repo::archive sources
    expect(cmd).toMatch(/^borg create .+ \/repo::test-\{now\} \/data$/)
    expect(cmd).toContain('--progress')
    expect(cmd).toContain('--stats')
    expect(cmd).toContain('--compression lz4')
    expect(cmd).toContain("--exclude '*.log'")
  })

  it('handles archive name with placeholders', () => {
    const archiveNames = [
      '{hostname}-{now}',
      'backup-{now}',
      '{user}-{hostname}-{now:%Y-%m-%d}',
      'daily-{now}',
    ]

    archiveNames.forEach((archiveName) => {
      const cmd = generateBorgCreateCommand({
        repositoryPath: '/repo',
        sourceDirs: ['/data'],
        archiveName,
      })

      expect(cmd).toContain(`/repo::${archiveName}`)
    })
  })

  it('generates command that can be visually verified', () => {
    // This test serves as a visual sanity check
    const options: BorgCommandOptions = {
      repositoryPath: '/backups/production',
      compression: 'zstd,6',
      excludePatterns: ['*.log', '*.tmp', '/cache/*'],
      sourceDirs: ['/data', '/home'],
      customFlags: '--one-file-system --exclude-caches',
      archiveName: 'prod-backup-{now}',
    }

    const cmd = generateBorgCreateCommand(options)

    // Log for manual verification during test run
    // console.log('Generated command:', cmd)

    expect(cmd).toBeTruthy()
    expect(cmd).toContain('borg create')
  })
})

describe('generateBorgInitCommand', () => {
  it('generates borg init for Borg 1', () => {
    const cmd = generateBorgInitCommand({
      repositoryPath: '/backups/repo',
      borgVersion: 1,
      encryption: 'repokey',
    })

    expect(cmd).toBe('borg init --encryption repokey /backups/repo')
  })

  it('generates borg2 repo-create for Borg 2', () => {
    const cmd = generateBorgInitCommand({
      repositoryPath: '/backups/repo',
      borgVersion: 2,
      encryption: 'repokey-aes-ocb',
    })

    expect(cmd).toBe(
      'borg2 -r /backups/repo repo-create --encryption aes256-ocb --key-location repokey'
    )
  })
})

describe('command quoting', () => {
  it('quotes the repository path, sources and excludes that need it', () => {
    const base = {
      repositoryPath: "/mnt/my repo/it's",
      excludePatterns: ['/tmp/my cache', '*.o'],
      sourceDirs: ['/data/my files', "/o'brien"],
      archiveName: 'a-{now}',
    }
    const quoted = ["--exclude '/tmp/my cache' --exclude '*.o'", "'/data/my files' '/o'\\''brien'"]
    const v1 = generateBorgCreateCommand(base)
    expect(v1).toContain("'/mnt/my repo/it'\\''s'::a-{now}")
    quoted.forEach((q) => expect(v1).toContain(q))
    const v2 = generateBorgCreateCommand({ ...base, borgVersion: 2 })
    expect(v2).toContain("-r '/mnt/my repo/it'\\''s' create")
    quoted.forEach((q) => expect(v2).toContain(q))
  })

  it('quotes the repository path in init commands', () => {
    expect(generateBorgInitCommand({ repositoryPath: '/mnt/my repo' })).toBe(
      "borg init --encryption repokey '/mnt/my repo'"
    )
    expect(generateBorgInitCommand({ repositoryPath: '/mnt/my repo', borgVersion: 2 })).toContain(
      "-r '/mnt/my repo' repo-create"
    )
  })
})

describe('isBorg2OnlyUrl', () => {
  it('matches the schemes only Borg 2 can open, at the start, in any case', () => {
    for (const url of ['sftp://h/r', ' HTTPS://h/r', 'rest://h/r', 's3:x', 'b2:x', 'rclone:r:x']) {
      expect(isBorg2OnlyUrl(url)).toBe(true)
    }
    for (const url of ['/backups/s3:x', 'ssh://h/r', 'file:///r', 'user@host:repo', '']) {
      expect(isBorg2OnlyUrl(url)).toBe(false)
    }
  })
})

describe('Borg 2 ssh:// paths', () => {
  it('reads a leading slash as absolute, Borg 1 spelling of the login directory as relative', () => {
    expect(borg2PathIsAbsolute('/srv/repo')).toBe(true)
    expect(borg2PathIsAbsolute('backups/repo')).toBe(false)
    expect(borg2PathIsAbsolute('/./backups/repo')).toBe(false)
    expect(borg2PathIsAbsolute('/.')).toBe(false)
  })

  it('writes a URL tail the way the form reads a path', () => {
    expect(borg2PathFromUrlTail('/backups/repo')).toBe('backups/repo')
    expect(borg2PathFromUrlTail('//srv/repo')).toBe('/srv/repo')
    expect(borg2PathFromUrlTail('/./backups/repo')).toBe('./backups/repo')
    // absolute stays absolute: Borg 2 reads //./srv/repo as /srv/repo
    expect(borg2PathFromUrlTail('//./srv/repo')).toBe('/srv/repo')
    // the login directory itself
    expect(borg2PathFromUrlTail('/')).toBe('.')
    expect(borg2PathFromUrlTail('')).toBe('.')
    expect(borg2PathIsAbsolute(borg2PathFromUrlTail('//.'))).toBe(true)
  })

  it('tells an absolute URL from a relative one', () => {
    expect(borg2SshUrlIsAbsolute('ssh://u@h:22//srv/repo')).toBe(true)
    expect(borg2SshUrlIsAbsolute('ssh://u@h/backups/repo')).toBe(false)
    expect(borg2SshUrlIsAbsolute('/srv/repo')).toBeNull()
  })

  it('builds the URL back from the form spelling', () => {
    expect(borg2SshUrl('u', 'h', 22, '/srv/repo')).toBe('ssh://u@h:22//srv/repo')
    expect(borg2SshUrl('u', 'h', 22, 'backups/repo')).toBe('ssh://u@h:22/backups/repo')
    expect(borg2SshUrl('u', 'h', 22, '/./backups/repo')).toBe('ssh://u@h:22/./backups/repo')
  })
})
