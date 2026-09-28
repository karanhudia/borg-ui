"""The gunicorn worker class the server runs under.

uvicorn waits for every open connection before the lifespan shutdown, and an
event stream never closes on its own, so without a bound the operations
runner kept claiming work until gunicorn's `--graceful-timeout` killed the
worker (#1166). After this many seconds uvicorn cancels what is still open
and runs the shutdown, which stops and drains the runner within the
remaining graceful window.
"""

from uvicorn.workers import UvicornWorker

GRACEFUL_SHUTDOWN_SECONDS = 5


class BorgUIWorker(UvicornWorker):
    CONFIG_KWARGS = {
        **UvicornWorker.CONFIG_KWARGS,
        "timeout_graceful_shutdown": GRACEFUL_SHUTDOWN_SECONDS,
    }
