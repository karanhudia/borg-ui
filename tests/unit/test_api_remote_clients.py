import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestRemoteClientsApi:
    def test_admin_can_manage_remote_clients(
        self, test_client: TestClient, admin_headers
    ):
        create_response = test_client.post(
            "/api/remote-clients",
            json={
                "id": "legacy-client-1",
                "name": "Studio NAS",
                "backend_url": "nas.local:9000",
            },
            headers=admin_headers,
        )

        assert create_response.status_code == 201
        created = create_response.json()
        assert created["id"] == "legacy-client-1"
        assert created["name"] == "Studio NAS"
        assert created["api_base_url"] == "http://nas.local:9000/api"
        assert created["web_base_url"] == "http://nas.local:9000"
        assert created["health"]["status"] == "unknown"
        assert created["health"]["compatibility"] == "unknown"
        assert created["created_at"].endswith("+00:00")
        assert created["updated_at"].endswith("+00:00")

        list_response = test_client.get("/api/remote-clients", headers=admin_headers)
        assert list_response.status_code == 200
        assert [client["id"] for client in list_response.json()] == ["legacy-client-1"]

        update_response = test_client.put(
            "/api/remote-clients/legacy-client-1",
            json={
                "name": "Studio NAS 2",
                "backend_url": "https://nas.example.com/borg/api",
            },
            headers=admin_headers,
        )

        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["id"] == "legacy-client-1"
        assert updated["name"] == "Studio NAS 2"
        assert updated["api_base_url"] == "https://nas.example.com/borg/api"
        assert updated["web_base_url"] == "https://nas.example.com/borg"

        health_response = test_client.patch(
            "/api/remote-clients/legacy-client-1/health",
            json={
                "status": "online",
                "checked_at": "2026-06-06T12:34:56+00:00",
                "app_version": "2.2.2-alpha.1",
                "borg_version": "borg 1.4.0",
                "borg2_version": "borg2 2.0.0",
                "error": None,
                "compatibility": "compatible",
                "compatibility_message": "Compatible",
            },
            headers=admin_headers,
        )

        assert health_response.status_code == 200
        health = health_response.json()["health"]
        assert health["status"] == "online"
        assert health["checked_at"] == "2026-06-06T12:34:56+00:00"
        assert health["app_version"] == "2.2.2-alpha.1"
        assert health["borg_version"] == "borg 1.4.0"
        assert health["borg2_version"] == "borg2 2.0.0"
        assert health["compatibility"] == "compatible"
        assert health["compatibility_message"] == "Compatible"

        delete_response = test_client.delete(
            "/api/remote-clients/legacy-client-1", headers=admin_headers
        )
        assert delete_response.status_code == 204

        final_list = test_client.get("/api/remote-clients", headers=admin_headers)
        assert final_list.status_code == 200
        assert final_list.json() == []

    @pytest.mark.parametrize(
        ("method", "path", "json"),
        [
            ("get", "/api/remote-clients", None),
            (
                "post",
                "/api/remote-clients",
                {"name": "Office", "backend_url": "office.example.com"},
            ),
            (
                "put",
                "/api/remote-clients/client-1",
                {"name": "Office", "backend_url": "office.example.com"},
            ),
            (
                "patch",
                "/api/remote-clients/client-1/health",
                {"status": "offline", "compatibility": "unknown"},
            ),
            ("delete", "/api/remote-clients/client-1", None),
        ],
    )
    def test_non_admin_cannot_manage_remote_clients(
        self,
        test_client: TestClient,
        auth_headers,
        method: str,
        path: str,
        json: dict | None,
    ):
        request = getattr(test_client, method)
        if json is None:
            response = request(path, headers=auth_headers)
        else:
            response = request(path, json=json, headers=auth_headers)

        assert response.status_code == 403

    def test_rejects_invalid_remote_client_url(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.post(
            "/api/remote-clients",
            json={"name": "Broken", "backend_url": "ftp://example.com"},
            headers=admin_headers,
        )

        assert response.status_code == 422
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.remoteClients.invalidUrl"
        )

    def test_rejects_duplicate_remote_client_id(
        self, test_client: TestClient, admin_headers
    ):
        payload = {
            "id": "legacy-client-1",
            "name": "Studio NAS",
            "backend_url": "nas.local:9000",
        }
        first_response = test_client.post(
            "/api/remote-clients", json=payload, headers=admin_headers
        )
        assert first_response.status_code == 201

        duplicate_response = test_client.post(
            "/api/remote-clients", json=payload, headers=admin_headers
        )

        assert duplicate_response.status_code == 409
        assert (
            duplicate_response.json()["detail"]["key"]
            == "backend.errors.remoteClients.alreadyExists"
        )
