from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.services.source_discovery import scan_database_sources


@pytest.mark.unit
def test_scan_database_sources_detects_postgres_process_data_dir():
    result = scan_database_sources(
        processes=[
            {
                "name": "postgres",
                "cmdline": ["postgres", "-D", "/var/lib/postgresql/16/main"],
            }
        ],
        path_exists=lambda _path: False,
    )

    postgres = next(item for item in result.databases if item.engine == "postgresql")

    assert postgres.status == "running"
    assert postgres.source_directories == ["/var/lib/postgresql/16/main"]
    assert postgres.service_name == "postgresql"
    assert postgres.confidence == "high"
    assert "DB_SERVICE_NAME:-postgresql" in postgres.pre_backup_script.content
    assert "systemctl stop" in postgres.pre_backup_script.content
    assert "systemctl start" in postgres.post_backup_script.content


@pytest.mark.unit
def test_scan_database_sources_exposes_container_source_as_planned():
    result = scan_database_sources(processes=[], path_exists=lambda _path: False)

    source_types = {source_type.id: source_type for source_type in result.source_types}

    assert source_types["database"].enabled is True
    assert source_types["container"].enabled is False
    assert source_types["container"].planned is True
    assert {template.engine for template in result.templates} >= {
        "postgresql",
        "mysql",
        "mongodb",
        "redis",
    }


@pytest.mark.unit
def test_source_discovery_api_returns_database_scan(
    test_client: TestClient, admin_headers
):
    with patch("app.api.source_discovery.scan_database_sources") as scan:
        scan.return_value = scan_database_sources(
            processes=[
                {
                    "name": "mongod",
                    "cmdline": ["mongod", "--dbpath", "/srv/mongodb"],
                }
            ],
            path_exists=lambda _path: False,
        )

        response = test_client.get(
            "/api/source-discovery/databases", headers=admin_headers
        )

    assert response.status_code == 200
    data = response.json()
    assert data["databases"][0]["engine"] == "mongodb"
    assert data["databases"][0]["source_directories"] == ["/srv/mongodb"]
    assert data["source_types"][1]["id"] == "database"
