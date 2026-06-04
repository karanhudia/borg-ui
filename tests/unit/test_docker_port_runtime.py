from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _workflow_step_block(workflow: str, step_name: str) -> str:
    step_header = f"      - name: {step_name}"
    step_start = workflow.index(step_header)
    next_step_start = workflow.find("\n      - name:", step_start + len(step_header))
    if next_step_start == -1:
        return workflow[step_start:]
    return workflow[step_start:next_step_start]


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
    smoke_step = _workflow_step_block(workflow, "Smoke test amd64 app image")

    assert "-p 18088:8088" in smoke_step
    assert "-e PORT=8088" in smoke_step
    assert "http://127.0.0.1:18088/" in smoke_step
    assert "-p 18081:8081" not in smoke_step
