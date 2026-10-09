"""#1386: an agent repository's hooks are agent scripts.

The API assigns a script the agent publishes to an agent repository and
refuses what the repository's executor cannot run: an inline shell script or
a library script on an agent repository, an agent script on a server one.
"""

from unittest.mock import patch

import pytest

from app.core.security import get_password_hash
from app.database.models import AgentMachine, Repository, RepositoryScript, Script

REFUSED = "backend.errors.scripts.agentRepositoryRunsAgentScripts"
NEEDS_AGENT = "backend.errors.scripts.agentScriptNeedsAgentRepository"


def _agent(db):
    agent = AgentMachine(
        name="Host",
        agent_id="agt_host",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.init", "backup.create", "script.run"],
    )
    db.add(agent)
    db.commit()
    return agent


def _repo(db, *, agent=None, **kw):
    repo = Repository(
        name=kw.pop("name", "repo"),
        path=kw.pop("path", "/repos/repo"),
        encryption="none",
        repository_type="local",
        executor_type="agent" if agent else "server",
        execution_target="agent" if agent else "local",
        agent_machine_id=agent.id if agent else None,
        **kw,
    )
    db.add(repo)
    db.commit()
    return repo


def _library_script(db):
    script = Script(name="stop-db", file_path="library/stop-db.sh", category="custom")
    db.add(script)
    db.commit()
    return script


def _assign(client, headers, repo, **body):
    return client.post(
        f"/api/repositories/{repo.id}/scripts",
        json={"hook_type": "pre-backup", **body},
        headers=headers,
    )


@pytest.mark.unit
class TestAssignment:
    def test_assigns_an_agent_script_to_an_agent_repository(
        self, test_client, admin_headers, test_db
    ):
        repo = _repo(test_db, agent=_agent(test_db))

        response = _assign(
            test_client,
            admin_headers,
            repo,
            agent_script_name=" backup-postgres ",
            continue_on_error=False,
            custom_timeout=900,
        )

        assert response.status_code == 200, response.text
        row = test_db.query(RepositoryScript).one()
        assert (row.script_id, row.agent_script_name) == (None, "backup-postgres")
        assert (row.continue_on_error, row.custom_timeout) == (False, 900)
        listed = test_client.get(
            f"/api/repositories/{repo.id}/scripts", headers=admin_headers
        ).json()
        assert listed["post_backup"] == []
        [hook] = listed["pre_backup"]
        assert hook["is_agent_script"] is True
        assert hook["script_name"] == "backup-postgres"
        assert hook["default_run_on"] == "always"
        assert hook["parameters"] == []

    def test_refuses_the_same_agent_script_twice(
        self, test_client, admin_headers, test_db
    ):
        repo = _repo(test_db, agent=_agent(test_db))
        _assign(test_client, admin_headers, repo, agent_script_name="dump")

        response = _assign(test_client, admin_headers, repo, agent_script_name="dump")

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == (
            "backend.errors.scripts.scriptAlreadyAssigned"
        )

    @pytest.mark.parametrize("name", ["../dump", "bin/dump", "a\\b", "x" * 256])
    def test_refuses_a_name_that_cannot_be_an_agent_script(
        self, test_client, admin_headers, test_db, name
    ):
        repo = _repo(test_db, agent=_agent(test_db))

        response = _assign(test_client, admin_headers, repo, agent_script_name=name)

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == (
            "backend.errors.scripts.invalidAgentScriptName"
        )

    def test_refuses_a_library_script_on_an_agent_repository(
        self, test_client, admin_headers, test_db
    ):
        repo = _repo(test_db, agent=_agent(test_db))
        script = _library_script(test_db)

        response = _assign(test_client, admin_headers, repo, script_id=script.id)

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == REFUSED
        assert test_db.query(RepositoryScript).count() == 0

    def test_refuses_an_agent_script_on_a_server_repository(
        self, test_client, admin_headers, test_db
    ):
        repo = _repo(test_db)

        response = _assign(test_client, admin_headers, repo, agent_script_name="dump")

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == NEEDS_AGENT

    @pytest.mark.parametrize("both", [True, False])
    def test_needs_exactly_one_script(self, test_client, admin_headers, test_db, both):
        repo = _repo(test_db, agent=_agent(test_db))
        script = _library_script(test_db)
        body = {"agent_script_name": "dump", "script_id": script.id} if both else {}

        response = _assign(test_client, admin_headers, repo, **body)

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == (
            "backend.errors.scripts.hookScriptRequired"
        )

    def test_updates_an_agent_hook_and_ignores_parameter_values(
        self, test_client, admin_headers, test_db
    ):
        repo = _repo(test_db, agent=_agent(test_db))
        hook_id = _assign(
            test_client, admin_headers, repo, agent_script_name="dump"
        ).json()["id"]

        response = test_client.put(
            f"/api/repositories/{repo.id}/scripts/{hook_id}",
            json={"custom_run_on": "failure", "parameter_values": {"a": "b"}},
            headers=admin_headers,
        )

        assert response.status_code == 200, response.text
        row = test_db.get(RepositoryScript, hook_id)
        test_db.refresh(row)
        assert (row.custom_run_on, row.parameter_values) == ("failure", None)

    def test_refuses_enabling_a_library_script_on_an_agent_repository(
        self, test_client, admin_headers, test_db
    ):
        repo = _repo(test_db, agent=_agent(test_db))
        row = RepositoryScript(
            repository_id=repo.id,
            script_id=_library_script(test_db).id,
            hook_type="pre-backup",
            enabled=False,
        )
        test_db.add(row)
        test_db.commit()

        response = test_client.put(
            f"/api/repositories/{repo.id}/scripts/{row.id}",
            json={"enabled": True},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == REFUSED


@pytest.mark.unit
class TestRepositoryInlineScripts:
    def test_create_refuses_an_inline_script_for_an_agent_repository(
        self, test_client, admin_headers, test_db
    ):
        agent = _agent(test_db)

        response = test_client.post(
            "/api/repositories/",
            json={
                "name": "Agent Repo",
                "path": "/agent/repo",
                "encryption": "none",
                "compression": "lz4",
                "borg_version": 1,
                "source_directories": ["/home/user/docs"],
                "execution_target": "agent",
                "agent_machine_id": agent.id,
                "pre_backup_script": "systemctl stop postgresql",
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == REFUSED
        assert test_db.query(Repository).count() == 0

    def test_update_refuses_a_new_inline_script(
        self, test_client, admin_headers, test_db
    ):
        repo = _repo(test_db, agent=_agent(test_db))

        with patch("app.api.repositories.mqtt_service.sync_state_with_db"):
            response = test_client.put(
                f"/api/repositories/{repo.id}",
                json={"post_backup_script": "systemctl start postgresql"},
                headers=admin_headers,
            )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == REFUSED
        test_db.refresh(repo)
        assert repo.post_backup_script is None

    def test_update_takes_a_stored_inline_script_sent_back_or_cleared(
        self, test_client, admin_headers, test_db
    ):
        """The form sends the stored value back with every save; an agent
        repository that holds one from before can still be saved, and the
        script removed."""
        repo = _repo(test_db, agent=_agent(test_db), pre_backup_script="old")

        with patch("app.api.repositories.mqtt_service.sync_state_with_db"):
            kept = test_client.put(
                f"/api/repositories/{repo.id}",
                json={"pre_backup_script": "old", "post_backup_script": ""},
                headers=admin_headers,
            )
            cleared = test_client.put(
                f"/api/repositories/{repo.id}",
                json={"pre_backup_script": ""},
                headers=admin_headers,
            )

        assert kept.status_code == 200, kept.text
        assert cleared.status_code == 200, cleared.text
        test_db.refresh(repo)
        assert repo.pre_backup_script == ""

    @pytest.mark.parametrize("library", [False, True])
    def test_switching_to_an_agent_refuses_server_scripts(
        self, test_client, admin_headers, test_db, library
    ):
        agent = _agent(test_db)
        repo = _repo(test_db, pre_backup_script=None if library else "stop db")
        if library:
            test_db.add(
                RepositoryScript(
                    repository_id=repo.id,
                    script_id=_library_script(test_db).id,
                    hook_type="post-backup",
                )
            )
            test_db.commit()

        with patch("app.api.repositories.mqtt_service.sync_state_with_db"):
            response = test_client.put(
                f"/api/repositories/{repo.id}",
                json={"executor_type": "agent", "agent_machine_id": agent.id},
                headers=admin_headers,
            )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == REFUSED
        test_db.refresh(repo)
        assert repo.executor_type == "server"

    def test_switching_to_an_agent_can_clear_the_inline_script(
        self, test_client, admin_headers, test_db
    ):
        agent = _agent(test_db)
        repo = _repo(test_db, pre_backup_script="stop db")

        with patch("app.api.repositories.mqtt_service.sync_state_with_db"):
            response = test_client.put(
                f"/api/repositories/{repo.id}",
                json={
                    "executor_type": "agent",
                    "agent_machine_id": agent.id,
                    "pre_backup_script": "",
                },
                headers=admin_headers,
            )

        assert response.status_code == 200, response.text
        test_db.refresh(repo)
        assert (repo.executor_type, repo.pre_backup_script) == ("agent", "")

    def test_switching_to_the_server_refuses_agent_scripts(
        self, test_client, admin_headers, test_db
    ):
        repo = _repo(test_db, agent=_agent(test_db))
        test_db.add(
            RepositoryScript(
                repository_id=repo.id,
                agent_script_name="dump",
                hook_type="pre-backup",
            )
        )
        test_db.commit()

        with patch("app.api.repositories.mqtt_service.sync_state_with_db"):
            response = test_client.put(
                f"/api/repositories/{repo.id}",
                json={"executor_type": "server"},
                headers=admin_headers,
            )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == NEEDS_AGENT


def _operator_headers(db, repo, role):
    from datetime import datetime, timezone

    from app.core.security import create_access_token
    from app.database.models import User, UserRepositoryPermission

    user = User(
        username=f"user-{role}",
        password_hash=get_password_hash("x"),
        is_active=True,
        role="viewer",
    )
    db.add(user)
    db.commit()
    db.add(
        UserRepositoryPermission(
            user_id=user.id,
            repository_id=repo.id,
            role=role,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    token = create_access_token(data={"sub": user.username})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.unit
class TestRepositoryAgentScripts:
    """The picker asks the repository's saved agent, for the repository's
    operators: the managed-machines probe is for admins only."""

    def test_an_operator_lists_the_scripts_of_the_repositorys_agent(
        self, test_client, test_db, monkeypatch
    ):
        from app.services.agent_connection_manager import agent_connection_manager

        agent = _agent(test_db)
        repo = _repo(test_db, agent=agent)
        asked = []

        async def fake_send_command(agent_machine_id, *, command, **kwargs):
            asked.append((agent_machine_id, command))
            return {"scripts": [{"name": "dump", "description": " pg "}, {"x": 1}]}

        monkeypatch.setattr(agent_connection_manager, "send_command", fake_send_command)

        response = test_client.get(
            f"/api/repositories/{repo.id}/agent-scripts",
            headers=_operator_headers(test_db, repo, "operator"),
        )

        assert response.status_code == 200, response.text
        assert response.json() == {
            "scripts": [{"name": "dump", "description": "pg"}],
            "agent_online": True,
        }
        assert asked == [(agent.id, "agent.list_scripts")]

    def test_a_viewer_is_refused(self, test_client, test_db):
        repo = _repo(test_db, agent=_agent(test_db))

        response = test_client.get(
            f"/api/repositories/{repo.id}/agent-scripts",
            headers=_operator_headers(test_db, repo, "viewer"),
        )

        assert response.status_code == 403

    def test_a_server_repository_has_none(self, test_client, admin_headers, test_db):
        repo = _repo(test_db)

        response = test_client.get(
            f"/api/repositories/{repo.id}/agent-scripts", headers=admin_headers
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == NEEDS_AGENT
