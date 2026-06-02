from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_entrypoint_binds_server_to_configured_port() -> None:
    entrypoint = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")

    assert "PORT=${PORT:-8081}" in entrypoint
    assert '--port "${PORT}"' in entrypoint
    assert "--bind 0.0.0.0:${PORT}" in entrypoint


def test_production_compose_passes_port_to_container_and_healthcheck() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert '"${PORT:-8081}:${PORT:-8081}"' in compose
    assert "PORT=${PORT:-8081}" in compose
    assert "curl -f http://localhost:$${PORT:-8081}/" in compose


def test_release_smoke_exercises_non_default_runtime_port() -> None:
    workflow = (ROOT / ".github" / "workflows" / "docker-publish.yml").read_text(
        encoding="utf-8"
    )

    assert "-p 18088:8088" in workflow
    assert "-e PORT=8088" in workflow
    assert "http://127.0.0.1:18088/" in workflow
    assert "-p 18081:8081" not in workflow
