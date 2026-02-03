import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import CommandPreview from '../CommandPreview'

describe('CommandPreview', () => {
  describe('Local source backups', () => {
    it('renders init and backup steps for create mode', () => {
      render(
        <CommandPreview
          mode="create"
          repositoryPath="/backups/repo"
          encryption="repokey"
          compression="lz4"
          sourceDirs={['/home/user/data']}
          repositoryMode="full"
          dataSource="local"
        />
      )

      expect(screen.getByText('How backup will work:')).toBeInTheDocument()
      expect(screen.getByText('Step 1: Initialize Repository')).toBeInTheDocument()
      expect(screen.getByText('Step 2: Run Backup')).toBeInTheDocument()
      expect(screen.getByText(/borg init --encryption repokey/)).toBeInTheDocument()
      expect(screen.getByText(/borg create/)).toBeInTheDocument()
    })

    it('renders only backup step for import mode (no step number)', () => {
      render(
        <CommandPreview
          mode="import"
          repositoryPath="/backups/repo"
          compression="zstd"
          sourceDirs={['/home/user/data']}
          repositoryMode="full"
          dataSource="local"
        />
      )

      expect(screen.getByText('How backup works:')).toBeInTheDocument()
      expect(screen.getByText('Run Backup')).toBeInTheDocument()
      expect(screen.queryByText(/Step 1/)).not.toBeInTheDocument()
      expect(screen.getByText(/This command will be used for future backups/)).toBeInTheDocument()
    })

    it('does not show backup step for observe mode', () => {
      render(
        <CommandPreview
          mode="create"
          repositoryPath="/backups/repo"
          encryption="none"
          repositoryMode="observe"
          dataSource="local"
        />
      )

      expect(screen.getByText('Step 1: Initialize Repository')).toBeInTheDocument()
      expect(screen.queryByText(/Run Backup/)).not.toBeInTheDocument()
    })

    it('handles SSH repository type correctly', () => {
      render(
        <CommandPreview
          mode="create"
          repositoryPath="/backups/repo"
          repositoryLocation="ssh"
          host="backup-server.com"
          username="backup"
          port={2222}
          encryption="repokey-blake2"
          sourceDirs={['/data']}
          repositoryMode="full"
          dataSource="local"
        />
      )

      // Should appear in both init and create commands
      const matches = screen.getAllByText(/ssh:\/\/backup@backup-server.com:2222/)
      expect(matches.length).toBeGreaterThanOrEqual(1)
    })

    it('includes remote-path flag when specified', () => {
      render(
        <CommandPreview
          mode="create"
          repositoryPath="/backups/repo"
          encryption="repokey"
          remotePath="/usr/local/bin/borg"
          sourceDirs={['/data']}
          repositoryMode="full"
          dataSource="local"
        />
      )

      // Should appear in init command
      const matches = screen.getAllByText(/--remote-path/)
      expect(matches.length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Remote source backups (SSHFS)', () => {
    const sshConnection = {
      username: 'admin',
      host: '192.168.1.100',
      port: 22,
    }

    it('renders all steps for create mode with remote source', () => {
      render(
        <CommandPreview
          mode="create"
          repositoryPath="/local/backups"
          encryption="repokey"
          compression="lz4"
          sourceDirs={['/home/admin/documents']}
          repositoryMode="full"
          dataSource="remote"
          sourceSshConnection={sshConnection}
        />
      )

      expect(screen.getByText('How backup will work:')).toBeInTheDocument()
      expect(screen.getByText('Step 1: Initialize Repository')).toBeInTheDocument()
      expect(screen.getByText('Step 2: Mount Remote Directory')).toBeInTheDocument()
      expect(screen.getByText('Step 3: Run Backup')).toBeInTheDocument()
      expect(screen.getByText('Step 4: Cleanup')).toBeInTheDocument()
      expect(screen.getByText(/sshfs admin@192.168.1.100/)).toBeInTheDocument()
      expect(screen.getByText(/fusermount -u/)).toBeInTheDocument()
    })

    it('renders mount, backup, cleanup steps for import mode with remote source', () => {
      render(
        <CommandPreview
          mode="import"
          repositoryPath="/local/backups"
          compression="zstd"
          sourceDirs={['/var/data']}
          repositoryMode="full"
          dataSource="remote"
          sourceSshConnection={sshConnection}
        />
      )

      expect(screen.getByText('How backup works:')).toBeInTheDocument()
      expect(screen.getByText('Step 1: Mount Remote Directory')).toBeInTheDocument()
      expect(screen.getByText('Step 2: Run Backup')).toBeInTheDocument()
      expect(screen.getByText('Step 3: Cleanup')).toBeInTheDocument()
      expect(screen.queryByText(/Initialize Repository/)).not.toBeInTheDocument()
    })

    it('extracts basename from source directory for borg command', () => {
      render(
        <CommandPreview
          mode="import"
          repositoryPath="/backups"
          sourceDirs={['/home/user/my-documents']}
          repositoryMode="full"
          dataSource="remote"
          sourceSshConnection={sshConnection}
        />
      )

      // The borg create command should use the basename 'my-documents'
      // May appear in both sshfs mount and borg create commands
      const matches = screen.getAllByText(/my-documents/)
      expect(matches.length).toBeGreaterThanOrEqual(1)
    })

    it('includes port in sshfs command', () => {
      const customPortConnection = {
        username: 'user',
        host: 'server.com',
        port: 2222,
      }

      render(
        <CommandPreview
          mode="import"
          repositoryPath="/backups"
          sourceDirs={['/data']}
          repositoryMode="full"
          dataSource="remote"
          sourceSshConnection={customPortConnection}
        />
      )

      expect(screen.getByText(/-p 2222/)).toBeInTheDocument()
    })

    it('shows helpful descriptions for each step', () => {
      render(
        <CommandPreview
          mode="import"
          repositoryPath="/backups"
          sourceDirs={['/data']}
          repositoryMode="full"
          dataSource="remote"
          sourceSshConnection={sshConnection}
        />
      )

      expect(screen.getByText(/Temporarily mounts remote directory via SSHFS/)).toBeInTheDocument()
      expect(screen.getByText(/Archives preserve original paths/)).toBeInTheDocument()
      expect(
        screen.getByText(/Unmounts remote directory after backup completes/)
      ).toBeInTheDocument()
    })
  })

  describe('Edge cases', () => {
    it('uses default source path when none provided', () => {
      render(
        <CommandPreview
          mode="create"
          repositoryPath="/backups"
          encryption="repokey"
          sourceDirs={[]}
          repositoryMode="full"
          dataSource="local"
        />
      )

      expect(screen.getByText(/\/path\/to\/source/)).toBeInTheDocument()
    })

    it('uses default repository path when none provided', () => {
      render(
        <CommandPreview
          mode="create"
          repositoryPath=""
          encryption="repokey"
          sourceDirs={['/data']}
          repositoryMode="full"
          dataSource="local"
        />
      )

      // Default path appears in both init and create commands
      const matches = screen.getAllByText(/\/path\/to\/repository/)
      expect(matches.length).toBeGreaterThanOrEqual(1)
    })

    it('handles remote source without SSH connection gracefully', () => {
      render(
        <CommandPreview
          mode="import"
          repositoryPath="/backups"
          sourceDirs={['/data']}
          repositoryMode="full"
          dataSource="remote"
          sourceSshConnection={null}
        />
      )

      // Should fall back to local source display
      expect(screen.getByText('Run Backup')).toBeInTheDocument()
      expect(screen.queryByText(/Mount Remote Directory/)).not.toBeInTheDocument()
    })
  })
})
