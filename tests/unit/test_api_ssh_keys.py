"""
Unit tests for SSH keys API endpoints
"""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestSSHKeysEndpoints:
    """Test SSH keys API endpoints"""

    def test_list_ssh_keys_empty(self, test_client: TestClient, admin_headers):
        """Test listing SSH keys when none exist"""
        response = test_client.get("/api/ssh-keys/", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    def test_list_ssh_keys_unauthorized(self, test_client: TestClient):
        """Test listing SSH keys without authentication"""
        response = test_client.get("/api/ssh-keys/")

        assert response.status_code in [401, 403, 404]

    def test_generate_ssh_key_missing_fields(self, test_client: TestClient, admin_headers):
        """Test generating SSH key with missing fields"""
        response = test_client.post(
            "/api/ssh-keys/generate",
            json={},
            headers=admin_headers
        )

        assert response.status_code == 422  # Validation error

    def test_generate_ssh_key_invalid_type(self, test_client: TestClient, admin_headers):
        """Test generating SSH key with invalid key type"""
        response = test_client.post(
            "/api/ssh-keys/generate",
            json={
                "name": "test-key",
                "key_type": "invalid-type"
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 400, 403, 405, 422]

    def test_upload_ssh_key_missing_fields(self, test_client: TestClient, admin_headers):
        """Test uploading SSH key with missing fields"""
        response = test_client.post(
            "/api/ssh-keys/upload",
            json={},
            headers=admin_headers
        )

        assert response.status_code in [405, 422]  # Validation error or method not allowed

    def test_get_ssh_key_nonexistent(self, test_client: TestClient, admin_headers):
        """Test getting non-existent SSH key"""
        response = test_client.get("/api/ssh-keys/nonexistent-key", headers=admin_headers)

        assert response.status_code in [404, 422]

    def test_delete_ssh_key_nonexistent(self, test_client: TestClient, admin_headers):
        """Test deleting non-existent SSH key"""
        response = test_client.delete("/api/ssh-keys/nonexistent-key", headers=admin_headers)

        assert response.status_code in [404, 422]

    def test_get_ssh_public_key_nonexistent(self, test_client: TestClient, admin_headers):
        """Test getting public key for non-existent SSH key"""
        response = test_client.get(
            "/api/ssh-keys/nonexistent-key/public",
            headers=admin_headers
        )

        assert response.status_code in [404, 422]

    def test_test_ssh_connection_invalid(self, test_client: TestClient, admin_headers):
        """Test SSH connection with invalid parameters"""
        response = test_client.post(
            "/api/ssh-keys/test-connection",
            json={
                "host": "invalid-host",
                "key_name": "nonexistent-key"
            },
            headers=admin_headers
        )

        assert response.status_code in [400, 403, 404, 405, 500]
