"""
Unit tests for package management API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.database.models import InstalledPackage, PackageInstallJob


@pytest.mark.unit
class TestPackagesAPI:
    """Test package management endpoints"""

    def test_list_packages_empty(self, test_client: TestClient, admin_headers):
        response = test_client.get("/api/packages/", headers=admin_headers)

        assert response.status_code == 200
        assert response.json() == []

    def test_create_package_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        response = test_client.post(
            "/api/packages/",
            json={
                "name": "wakeonlan",
                "install_command": "apt-get install -y wakeonlan",
                "description": "Wake-on-LAN utility",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "wakeonlan"
        assert data["status"] == "pending"
        assert data["created_at"].endswith("+00:00")
        assert data["updated_at"].endswith("+00:00")

        package = (
            test_db.query(InstalledPackage)
            .filter(InstalledPackage.name == "wakeonlan")
            .first()
        )
        assert package is not None
        assert package.install_command == "apt-get install -y wakeonlan"

    def test_create_package_duplicate_returns_400(
        self, test_client: TestClient, admin_headers, test_db
    ):
        package = InstalledPackage(
            name="duplicated-package",
            install_command="apt-get install -y duplicated-package",
            description="Existing package",
        )
        test_db.add(package)
        test_db.commit()

        response = test_client.post(
            "/api/packages/",
            json={
                "name": "duplicated-package",
                "install_command": "apt-get install -y duplicated-package",
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.packages.packageAlreadyExists"
        )

    def test_update_package_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        package = InstalledPackage(
            name="old-name",
            install_command="apt-get install -y old-name",
            description="Old package",
        )
        test_db.add(package)
        test_db.commit()
        test_db.refresh(package)

        response = test_client.put(
            f"/api/packages/{package.id}",
            json={
                "name": "new-name",
                "install_command": "apt-get install -y new-name",
                "description": "Updated package",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "new-name"
        assert data["description"] == "Updated package"

    def test_update_package_not_found(self, test_client: TestClient, admin_headers):
        response = test_client.put(
            "/api/packages/999999",
            json={
                "name": "missing",
                "install_command": "apt-get install -y missing",
            },
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.packages.packageNotFound"
        )

    def test_install_package_starts_new_job(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        package = InstalledPackage(
            name="htop",
            install_command="apt-get install -y htop",
            description="Process viewer",
        )
        test_db.add(package)
        test_db.commit()
        test_db.refresh(package)

        job = PackageInstallJob(id=99, package_id=package.id, status="installing")

        with patch(
            "app.api.packages.package_service.start_install_job",
            new=AsyncMock(return_value=job),
        ) as start_job:
            response = test_client.post(
                f"/api/packages/{package.id}/install", headers=admin_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == 99
        assert data["status"] == "installing"
        start_job.assert_awaited_once()

    def test_install_package_existing_job_returns_existing_job(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        package = InstalledPackage(
            name="jq",
            install_command="apt-get install -y jq",
            description="JSON processor",
        )
        test_db.add(package)
        test_db.commit()
        test_db.refresh(package)

        existing_job = PackageInstallJob(package_id=package.id, status="pending")
        test_db.add(existing_job)
        test_db.commit()
        test_db.refresh(existing_job)

        with patch(
            "app.api.packages.package_service.start_install_job", new=AsyncMock()
        ) as start_job:
            response = test_client.post(
                f"/api/packages/{package.id}/install", headers=admin_headers
            )

        assert response.status_code == 200
        assert response.json()["job_id"] == existing_job.id
        assert response.json()["status"] == "pending"
        start_job.assert_not_awaited()

    def test_update_package_name_conflict_returns_400(
        self, test_client: TestClient, admin_headers, test_db
    ):
        package1 = InstalledPackage(
            name="pkg-one",
            install_command="apt-get install -y pkg-one",
        )
        package2 = InstalledPackage(
            name="pkg-two",
            install_command="apt-get install -y pkg-two",
        )
        test_db.add_all([package1, package2])
        test_db.commit()
        test_db.refresh(package1)

        response = test_client.put(
            f"/api/packages/{package1.id}",
            json={
                "name": "pkg-two",
                "install_command": "apt-get install -y pkg-one",
                "description": "conflicting",
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.packages.packageAlreadyExists"
        )

    def test_delete_package_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        package = InstalledPackage(
            name="to-delete",
            install_command="apt-get install -y to-delete",
        )
        test_db.add(package)
        test_db.commit()
        test_db.refresh(package)

        response = test_client.delete(
            f"/api/packages/{package.id}", headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json()["message"] == "backend.success.packages.packageRemoved"
        assert (
            test_db.query(InstalledPackage)
            .filter(InstalledPackage.id == package.id)
            .first()
            is None
        )

    def test_delete_package_not_found(self, test_client: TestClient, admin_headers):
        response = test_client.delete("/api/packages/999999", headers=admin_headers)

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.packages.packageNotFound"
        )

    def test_reinstall_package_resets_state_and_reuses_install_flow(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        package = InstalledPackage(
            name="reinstall-me",
            install_command="apt-get install -y reinstall-me",
            status="failed",
            install_log="old log",
            installed_at=datetime.utcnow(),
        )
        test_db.add(package)
        test_db.commit()
        test_db.refresh(package)

        mocked_install = AsyncMock(
            return_value={"job_id": 123, "message": "ok", "status": "pending"}
        )
        with patch("app.api.packages.install_package", new=mocked_install):
            response = test_client.post(
                f"/api/packages/{package.id}/reinstall", headers=admin_headers
            )

        assert response.status_code == 200
        assert response.json()["job_id"] == 123
        assert package.status == "pending"
        assert package.install_log is None
        assert package.installed_at is None
        mocked_install.assert_awaited_once_with(package.id, db=test_db)

    def test_get_job_status_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        package = InstalledPackage(
            name="job-package",
            install_command="apt-get install -y job-package",
        )
        test_db.add(package)
        test_db.commit()
        test_db.refresh(package)

        job = PackageInstallJob(
            package_id=package.id,
            status="installing",
            started_at=datetime(2026, 4, 27, 3, 0, 6),
            completed_at=datetime(2026, 4, 27, 3, 5, 6),
            exit_code=None,
            stdout="",
            stderr="",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/packages/jobs/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job.id
        assert data["package_id"] == package.id
        assert data["status"] == "installing"
        assert data["started_at"] == "2026-04-27T03:00:06+00:00"
        assert data["completed_at"] == "2026-04-27T03:05:06+00:00"

    def test_get_job_status_not_found(self, test_client: TestClient, admin_headers):
        response = test_client.get("/api/packages/jobs/999999", headers=admin_headers)

        assert response.status_code == 404
        assert response.json()["detail"]["key"] == "backend.errors.packages.jobNotFound"

    def test_list_jobs_returns_jobs(
        self, test_client: TestClient, admin_headers, test_db
    ):
        package = InstalledPackage(
            name="history-package",
            install_command="apt-get install -y history-package",
        )
        test_db.add(package)
        test_db.commit()
        test_db.refresh(package)

        job1 = PackageInstallJob(
            package_id=package.id,
            status="completed",
            started_at=datetime(2026, 4, 27, 3, 0, 6),
        )
        job2 = PackageInstallJob(package_id=package.id, status="failed")
        test_db.add_all([job1, job2])
        test_db.commit()

        response = test_client.get("/api/packages/jobs", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2
        completed_job = next(job for job in data if job["id"] == job1.id)
        assert completed_job["started_at"] == "2026-04-27T03:00:06+00:00"
        assert completed_job["created_at"].endswith("+00:00")


@pytest.mark.unit
class TestPackageInstallOperations:
    """Phase 6: package installs live in `operations` (spec 6.2, 6.3)."""

    def _package(self, test_db, name="ripgrep"):
        package = InstalledPackage(
            name=name, install_command=f"apt-get install -y {name}"
        )
        test_db.add(package)
        test_db.commit()
        test_db.refresh(package)
        return package

    def _operation(self, test_db, package, *, status="queued", run_id="run-1"):
        from app.database.models import Operation

        op = Operation(
            repository_id=None,
            kind="package_install",
            category="system",
            status=status,
            trigger="manual",
            priority=0,
            run_id=run_id,
            params={"package_id": package.id},
        )
        test_db.add(op)
        test_db.commit()
        test_db.refresh(op)
        return op

    def test_install_queues_an_operation(
        self, test_client: TestClient, admin_headers, test_db
    ):
        from app.database.models import Operation

        package = self._package(test_db)

        response = test_client.post(
            f"/api/packages/{package.id}/install", headers=admin_headers
        )

        operation = test_db.query(Operation).one()
        assert response.status_code == 200
        assert response.json()["job_id"] == operation.id
        assert operation.kind == "package_install"
        assert operation.params == {"package_id": package.id}
        assert test_db.query(PackageInstallJob).count() == 0

    def test_install_returns_the_in_flight_operation_instead_of_a_second_one(
        self, test_client: TestClient, admin_headers, test_db
    ):
        from app.database.models import Operation

        package = self._package(test_db, name="fd-find")
        existing = self._operation(test_db, package)

        with patch(
            "app.api.packages.package_service.start_install_job", new=AsyncMock()
        ) as start_job:
            response = test_client.post(
                f"/api/packages/{package.id}/install", headers=admin_headers
            )

        assert response.status_code == 200
        assert response.json()["job_id"] == existing.id
        assert response.json()["status"] == "pending"
        assert test_db.query(Operation).count() == 1
        start_job.assert_not_awaited()

    def test_job_status_serves_an_operation_with_its_captured_output(
        self, test_client: TestClient, admin_headers, test_db
    ):
        from app.services.operations.package_facade import PackageInstallFacade

        package = self._package(test_db, name="bat")
        op = self._operation(test_db, package, status="completed")
        job = PackageInstallFacade(test_db, op)
        job.exit_code = 0
        job.write_output("installed", "")
        test_db.commit()

        response = test_client.get(f"/api/packages/jobs/{op.id}", headers=admin_headers)

        body = response.json()
        assert response.status_code == 200
        assert body["id"] == op.id
        assert body["package_id"] == package.id
        assert body["status"] == "completed"
        assert body["exit_code"] == 0
        assert body["stdout"] == "installed"
        assert body["stderr"] == ""

    def test_job_status_still_serves_a_pre_phase_6_row(
        self, test_client: TestClient, admin_headers, test_db
    ):
        package = self._package(test_db, name="tree")
        job = PackageInstallJob(
            package_id=package.id, status="completed", exit_code=0, stdout="legacy out"
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/packages/jobs/{job.id}", headers=admin_headers
        )

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "completed"
        assert body["stdout"] == "legacy out"

    def test_job_list_unions_operations_and_legacy_rows(
        self, test_client: TestClient, admin_headers, test_db
    ):
        package = self._package(test_db, name="ncdu")
        op = self._operation(test_db, package, status="completed")
        legacy = PackageInstallJob(package_id=package.id, status="failed")
        test_db.add(legacy)
        test_db.commit()
        test_db.refresh(legacy)

        response = test_client.get("/api/packages/jobs", headers=admin_headers)

        body = response.json()
        assert response.status_code == 200
        assert {item["status"] for item in body} == {"completed", "failed"}
        assert {item["id"] for item in body} == {op.id, legacy.id}
