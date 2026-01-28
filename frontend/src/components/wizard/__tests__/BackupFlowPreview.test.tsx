import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import BackupFlowPreview from '../BackupFlowPreview'

const mockSshConnection = {
  id: 1,
  host: 'backup.server.com',
  username: 'backupuser',
  port: 22,
}

describe('BackupFlowPreview', () => {
  describe('Local to Local Backup', () => {
    it('shows correct summary text', () => {
      render(
        <BackupFlowPreview
          repositoryLocation="local"
          dataSource="local"
          repositoryPath="/backups/myrepo"
          sourceDirs={['/home/user']}
        />
      )

      expect(screen.getByText(/Back up local data to local repository/i)).toBeInTheDocument()
    })

    it('shows Borg UI Server as source', () => {
      render(
        <BackupFlowPreview
          repositoryLocation="local"
          dataSource="local"
          repositoryPath="/backups/myrepo"
          sourceDirs={['/home/user']}
        />
      )

      // Both source and repo show "Borg UI Server" in local-to-local
      const borgUIServers = screen.getAllByText('Borg UI Server')
      expect(borgUIServers.length).toBeGreaterThanOrEqual(1)
    })

    it('shows Borg UI Server as repository location', () => {
      render(
        <BackupFlowPreview
          repositoryLocation="local"
          dataSource="local"
          repositoryPath="/backups/myrepo"
          sourceDirs={['/home/user']}
        />
      )

      // Should show "Borg UI Server" twice - once for source and once for repo
      const borgUIServers = screen.getAllByText('Borg UI Server')
      expect(borgUIServers).toHaveLength(2)
    })

    it('shows repository path', () => {
      render(
        <BackupFlowPreview
          repositoryLocation="local"
          dataSource="local"
          repositoryPath="/backups/myrepo"
          sourceDirs={['/home/user']}
        />
      )

      expect(screen.getByText('/backups/myrepo')).toBeInTheDocument()
    })

    it('shows directory count', () => {
      render(
        <BackupFlowPreview
          repositoryLocation="local"
          dataSource="local"
          repositoryPath="/backups/myrepo"
          sourceDirs={['/home/user', '/var/data', '/opt/app']}
        />
      )

      expect(screen.getByText('3 dirs')).toBeInTheDocument()
    })

    it('shows singular "dir" for one directory', () => {
      render(
        <BackupFlowPreview
          repositoryLocation="local"
          dataSource="local"
          repositoryPath="/backups/myrepo"
          sourceDirs={['/home/user']}
        />
      )

      expect(screen.getByText('1 dir')).toBeInTheDocument()
    })
  })

  describe('Local to Remote Backup', () => {
    it('shows correct summary text', () => {
      render(
        <BackupFlowPreview
          repositoryLocation="ssh"
          dataSource="local"
          repositoryPath="/backups/myrepo"
          sourceDirs={['/home/user']}
          repoSshConnection={mockSshConnection}
        />
      )

      expect(screen.getByText(/Back up local data to remote repository/i)).toBeInTheDocument()
    })

    it('shows SSH connection details for repository', () => {
      render(
        <BackupFlowPreview
          repositoryLocation="ssh"
          dataSource="local"
          repositoryPath="/backups/myrepo"
          sourceDirs={['/home/user']}
          repoSshConnection={mockSshConnection}
        />
      )

      expect(screen.getByText('backupuser@backup.server.com')).toBeInTheDocument()
    })
  })

  describe('Remote to Local Backup (SSHFS)', () => {
    it('shows correct summary text', () => {
      render(
        <BackupFlowPreview
          repositoryLocation="local"
          dataSource="remote"
          repositoryPath="/backups/myrepo"
          sourceDirs={['/remote/data']}
          sourceSshConnection={mockSshConnection}
        />
      )

      expect(
        screen.getByText(/Back up remote data to local repository via SSHFS/i)
      ).toBeInTheDocument()
    })

    it('shows SSHFS intermediate node', () => {
      render(
        <BackupFlowPreview
          repositoryLocation="local"
          dataSource="remote"
          repositoryPath="/backups/myrepo"
          sourceDirs={['/remote/data']}
          sourceSshConnection={mockSshConnection}
        />
      )

      // "via SSHFS" appears in both summary text and flow
      const sshfsTexts = screen.getAllByText(/via SSHFS/i)
      expect(sshfsTexts.length).toBeGreaterThanOrEqual(1)
    })

    it('shows SSH connection details for source', () => {
      render(
        <BackupFlowPreview
          repositoryLocation="local"
          dataSource="remote"
          repositoryPath="/backups/myrepo"
          sourceDirs={['/remote/data']}
          sourceSshConnection={mockSshConnection}
        />
      )

      expect(screen.getByText('backupuser@backup.server.com')).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles empty repository path', () => {
      render(
        <BackupFlowPreview
          repositoryLocation="local"
          dataSource="local"
          repositoryPath=""
          sourceDirs={['/home/user']}
        />
      )

      // Should still render without error
      expect(screen.getByText(/Back up local data/i)).toBeInTheDocument()
    })

    it('handles empty source directories', () => {
      render(
        <BackupFlowPreview
          repositoryLocation="local"
          dataSource="local"
          repositoryPath="/backups/myrepo"
          sourceDirs={[]}
        />
      )

      // Should not show directory count when empty
      expect(screen.queryByText(/dir/i)).not.toBeInTheDocument()
    })

    it('shows Remote Client when source is remote but no connection provided', () => {
      render(
        <BackupFlowPreview
          repositoryLocation="local"
          dataSource="remote"
          repositoryPath="/backups/myrepo"
          sourceDirs={['/remote/data']}
        />
      )

      expect(screen.getByText('Remote Client')).toBeInTheDocument()
    })

    it('shows Remote Storage when repository is remote but no connection provided', () => {
      render(
        <BackupFlowPreview
          repositoryLocation="ssh"
          dataSource="local"
          repositoryPath="/backups/myrepo"
          sourceDirs={['/home/user']}
        />
      )

      expect(screen.getByText('Remote Storage')).toBeInTheDocument()
    })
  })
})
