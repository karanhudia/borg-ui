"""
Unit tests for SSH key deployment functionality
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.api.ssh_keys import deploy_ssh_key_with_copy_id
from app.database.models import SSHKey
from cryptography.fernet import Fernet
import base64


@pytest.mark.unit
class TestSSHKeyDeployment:
    """Test SSH key deployment with ssh-copy-id"""

    @pytest.mark.asyncio
    async def test_deploy_ssh_key_includes_sftp_flag(self):
        """Test that ssh-copy-id command includes -s flag for Hetzner Storage Box compatibility"""
        # Create a mock SSH key
        mock_key = MagicMock(spec=SSHKey)
        mock_key.id = 1
        mock_key.public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest test@test"

        # Encrypt a fake private key
        from app.config import settings
        encryption_key = settings.secret_key.encode()[:32]
        cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
        fake_private_key = "-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----\n"
        mock_key.private_key = cipher.encrypt(fake_private_key.encode()).decode()

        # Mock the subprocess to capture the command
        captured_cmd = []

        async def mock_subprocess(*cmd, **kwargs):
            # Store the command list
            captured_cmd.clear()
            captured_cmd.extend(cmd)
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"Success", b""))
            mock_process.returncode = 0
            return mock_process

        with patch('app.api.ssh_keys.asyncio.create_subprocess_exec', side_effect=mock_subprocess):
            with patch('app.api.ssh_keys.asyncio.wait_for') as mock_wait:
                mock_wait.return_value = (b"Success", b"")

                result = await deploy_ssh_key_with_copy_id(
                    mock_key,
                    "u331525-sub1.your-storagebox.de",
                    "u331525-sub1",
                    "test_password",
                    23
                )

        # Verify the command includes the -s flag
        assert "-s" in captured_cmd, "ssh-copy-id command should include -s flag for Hetzner compatibility"
        assert "ssh-copy-id" in captured_cmd, "Should use ssh-copy-id command"
        assert "-p" in captured_cmd, "Should include port flag"
        assert "23" in captured_cmd, "Should use port 23"

        # Verify success
        assert result["success"] == True, "Deployment should succeed"

    @pytest.mark.asyncio
    async def test_deploy_ssh_key_command_structure(self):
        """Test that the full ssh-copy-id command is structured correctly"""
        mock_key = MagicMock(spec=SSHKey)
        mock_key.id = 1
        mock_key.public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest test@test"

        from app.config import settings
        encryption_key = settings.secret_key.encode()[:32]
        cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
        fake_private_key = "-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----\n"
        mock_key.private_key = cipher.encrypt(fake_private_key.encode()).decode()

        captured_cmd = []

        async def mock_subprocess(*cmd, **kwargs):
            # Store the command list
            captured_cmd.clear()
            captured_cmd.extend(cmd)
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_process.returncode = 0
            return mock_process

        with patch('app.api.ssh_keys.asyncio.create_subprocess_exec', side_effect=mock_subprocess):
            with patch('app.api.ssh_keys.asyncio.wait_for') as mock_wait:
                mock_wait.return_value = (b"", b"")

                result = await deploy_ssh_key_with_copy_id(
                    mock_key,
                    "test.example.com",
                    "testuser",
                    "testpass",
                    22
                )

        # Verify command structure
        assert captured_cmd[0] == "sshpass", "Should start with sshpass"
        assert captured_cmd[1] == "-p", "Should have password flag"
        assert captured_cmd[2] == "testpass", "Should include password"
        assert captured_cmd[3] == "ssh-copy-id", "Should call ssh-copy-id"
        assert captured_cmd[4] == "-s", "Should include -s flag"
        assert "-i" in captured_cmd, "Should include identity file flag"
        assert "-o" in captured_cmd, "Should include SSH options"
        assert "StrictHostKeyChecking=no" in captured_cmd, "Should disable strict host key checking"
        assert "testuser@test.example.com" in captured_cmd, "Should include user@host"
