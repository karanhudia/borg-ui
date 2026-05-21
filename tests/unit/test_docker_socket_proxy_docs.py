from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_docker_hooks_docs_explain_socket_proxy_option() -> None:
    docs = (ROOT / "docs" / "docker-hooks.md").read_text()

    assert "docker-socket-proxy" in docs
    assert "DOCKER_HOST=tcp://docker-socket-proxy:2375" in docs
    assert "Tecnativa/docker-socket-proxy" in docs


def test_compose_file_points_hook_users_to_socket_proxy_option() -> None:
    compose = (ROOT / "docker-compose.yml").read_text()

    assert "docker-socket-proxy" in compose
    assert "DOCKER_HOST=tcp://docker-socket-proxy:2375" in compose
