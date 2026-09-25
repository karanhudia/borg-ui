import pytest


@pytest.mark.unit
def test_the_worker_bounds_the_wait_for_open_streams():
    """#1166: an event stream kept the lifespan shutdown, and with it the
    runner's stop, from running until gunicorn killed the worker."""
    from uvicorn import Config

    from app.gunicorn_worker import BorgUIWorker

    config = Config(app="app.main:app", **BorgUIWorker.CONFIG_KWARGS)
    assert config.timeout_graceful_shutdown == 5
