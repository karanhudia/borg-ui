/**
 * Tests for borgUtils.ts
 * Focus: Command generation that must produce valid Borg commands
 * WHY: Invalid commands = backup fails silently until user checks logs
 */

import { describe, it, expect } from 'vitest'
import { generateBorgCreateCommand, BorgCommandOptions } from './borgUtils'

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
